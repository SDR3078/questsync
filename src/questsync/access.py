"""Pluggable access policy: gate WHO may authenticate, keyed on the Habitica
User ID (the DAV username) — never the token. The check runs BEFORE the live
Habitica credential validation, so a denied user never triggers a Habitica call
(no credential-testing oracle, no wasted egress budget). A policy can only DENY;
it never grants more than valid Habitica creds already would.

Selected by QUESTSYNC_ACCESS_POLICY (default 'allowall'):
  allowall  — no-op; anyone with valid Habitica creds (today's behavior).
  allowlist — a static set of User IDs from QUESTSYNC_ALLOWLIST (comma list)
              and/or QUESTSYNC_ALLOWLIST_FILE (one id per line, re-read with a
              short TTL so edits — e.g. a mounted ConfigMap — take effect live).
  http      — ask an external endpoint "is user X allowed?" (for a hosted/paid
              control plane). Result cached for a short TTL; transient errors
              fail transient (raise), and are NEVER cached as a deny.

This module has NO billing and NO database dependency — allowlist/http are
generic and equally useful to a self-hoster (that invariant is CI-enforced).
"""
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


class TransientAccessError(RuntimeError):
    """Entitlement couldn't be determined right now (e.g. the policy endpoint is
    down). Callers must treat this as retry, never as a deny."""


class AllowAll:
    def check(self, user_id):
        return True


class Allowlist:
    def __init__(self, ids=None, path=None, ttl=30.0):
        self._static = set(ids or [])
        self._path = path
        self._ttl = ttl
        self._lock = threading.Lock()
        self._file_ids = set()
        self._file_at = -1.0

    def _from_file(self):
        if not self._path:
            return set()
        now = time.monotonic()
        with self._lock:
            if self._file_at >= 0 and (now - self._file_at) <= self._ttl:
                return self._file_ids
            try:
                with open(self._path, encoding="utf-8") as f:
                    self._file_ids = {ln.strip() for ln in f
                                      if ln.strip() and not ln.lstrip().startswith("#")}
            except OSError:
                pass                     # keep last-known set on a transient read error
            self._file_at = now
            return self._file_ids

    def check(self, user_id):
        return user_id in self._static or user_id in self._from_file()


class HttpPolicy:
    def __init__(self, url, ttl=60.0, timeout=5.0):
        self._url = url
        self._ttl = ttl
        self._timeout = timeout
        self._lock = threading.Lock()
        self._cache = {}                 # user_id -> (allowed, expiry_monotonic)

    def check(self, user_id):
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(user_id)
            if hit and hit[1] > now:
                return hit[0]
        allowed = self._query(user_id)   # may raise TransientAccessError (never cached)
        with self._lock:
            self._cache[user_id] = (allowed, now + self._ttl)
        return allowed

    def _query(self, user_id):
        sep = "&" if "?" in self._url else "?"
        url = self._url + sep + "user=" + urllib.parse.quote(user_id, safe="")
        try:
            with urllib.request.urlopen(url, timeout=self._timeout) as resp:
                return 200 <= resp.status < 300
        except urllib.error.HTTPError as e:
            if e.code in (401, 402, 403, 404):
                return False             # definitive: not entitled
            raise TransientAccessError("access endpoint HTTP %s" % e.code)
        except (urllib.error.URLError, OSError) as e:
            raise TransientAccessError(str(getattr(e, "reason", e)))


def get_policy(env=None):
    """Build the configured policy. Unset => allowall (self-host default);
    an unknown name fails closed (raises) rather than silently allowing all."""
    env = env if env is not None else os.environ
    kind = (env.get("QUESTSYNC_ACCESS_POLICY") or "allowall").strip().lower()
    if kind == "allowall":
        return AllowAll()
    if kind == "allowlist":
        ids = [x.strip() for x in env.get("QUESTSYNC_ALLOWLIST", "").split(",") if x.strip()]
        return Allowlist(ids=ids, path=env.get("QUESTSYNC_ALLOWLIST_FILE") or None,
                         ttl=float(env.get("QUESTSYNC_ALLOWLIST_TTL", "30")))
    if kind == "http":
        url = env.get("QUESTSYNC_ACCESS_HTTP_URL")
        if not url:
            raise RuntimeError("QUESTSYNC_ACCESS_POLICY=http requires QUESTSYNC_ACCESS_HTTP_URL")
        return HttpPolicy(url, ttl=float(env.get("QUESTSYNC_ACCESS_HTTP_TTL", "60")))
    raise RuntimeError("unknown QUESTSYNC_ACCESS_POLICY=%r (use allowall/allowlist/http)" % kind)
