"""QuestSync multi-user auth plugin.

DAV login = Habitica User ID, DAV password = Habitica API token. Credentials are
validated live against Habitica (GET /user); on success the token is cached in
`credstore` for the storage plugin and the User ID becomes the DAV principal, so
`[rights] owner_only` isolates each user to `/<user-id>/...`.

Radicale disables its own login cache for custom auth, so we cache validation
results here (keyed by login + a hash of the token). A rate limit (429) is never
treated as an invalid credential and is never cached as a failure.
"""
import hashlib
import os
import threading
import time

from radicale.auth import BaseAuth

from questsync import credstore
from questsync.access import get_policy
from questsync.habitica import HabiticaClient, HabiticaRateLimited
from questsync.settings import DEMO

_BASE = os.environ.get("HABITICA_BASE_URL", "https://habitica.com/api/v3")
_AUTHOR = os.environ.get("QUESTSYNC_CLIENT_AUTHOR", "")
_TTL = float(os.environ.get("QUESTSYNC_LOGIN_TTL", "300"))

_lock = threading.Lock()
_cache = {}                       # login -> (password_hash, ok, expiry_monotonic)

# Access gate (QUESTSYNC_ACCESS_POLICY): allowall (default) / allowlist / http.
_POLICY = get_policy()


def _hash(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


class Auth(BaseAuth):
    def _login(self, login, password):
        if DEMO:
            credstore.put(login, password or "demo")
            return login
        if not login or not password:
            return ""

        # Gate on the User ID BEFORE any Habitica call: a denied user never
        # touches Habitica (no credential-testing oracle, no wasted egress). A
        # transient policy error propagates as retry, never caches as a deny.
        if not _POLICY.check(login):
            return ""

        now = time.monotonic()
        phash = _hash(password)
        with _lock:
            hit = _cache.get(login)
        if hit and hit[0] == phash and hit[2] > now:
            if hit[1]:
                credstore.put(login, password)      # keep credstore warm
                return login
            return ""

        header = "%s-questsync" % (_AUTHOR or login)
        try:
            ok = HabiticaClient(login, password, client_header=header,
                                base_url=_BASE).validate()
        except HabiticaRateLimited:
            # A rate limit is NOT an invalid credential. Don't cache a negative,
            # don't return "" (which would be a 401); surface as transient.
            raise RuntimeError("Habitica rate limited; retry shortly")
        with _lock:
            _cache[login] = (phash, ok, now + (_TTL if ok else 5.0))
        if ok:
            credstore.put(login, password)          # in-memory, request-scoped
            return login
        return ""
