"""QuestSync multi-user auth plugin.

DAV login = Habitica User ID, DAV password = Habitica API token. Credentials are
validated live against Habitica (GET /user); on success the token is cached in
`credstore` for the storage plugin and the User ID becomes the DAV principal, so
`[rights] owner_only` isolates each user to `/<user-id>/...`.

Radicale's own `cache_logins` is disabled for custom auth plugins, so we cache
validation results here (keyed by login + a hash of the password) to avoid
hitting Habitica's rate-limited /user endpoint on every DAV request.

`QUESTSYNC_DEMO=1` accepts any credentials (for offline dev / CI).
"""
import hashlib
import os
import threading
import time

from radicale.auth import BaseAuth

from questsync import credstore
from questsync.habitica import HabiticaClient

_DEMO = os.environ.get("QUESTSYNC_DEMO") == "1"
_BASE = os.environ.get("HABITICA_BASE_URL", "https://habitica.com/api/v3")
_AUTHOR = os.environ.get("QUESTSYNC_CLIENT_AUTHOR", "")
_TTL = float(os.environ.get("QUESTSYNC_LOGIN_TTL", "300"))

_lock = threading.Lock()
_cache = {}                       # login -> (password_hash, ok, expiry_monotonic)


def _hash(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


class Auth(BaseAuth):
    def _login(self, login, password):
        if _DEMO:
            credstore.put(login, password or "demo")
            return login
        if not login or not password:
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
        ok = HabiticaClient(login, password, client_header=header,
                            base_url=_BASE).validate()
        with _lock:
            _cache[login] = (phash, ok, now + (_TTL if ok else 5.0))
        if ok:
            credstore.put(login, password)          # in-memory only
            return login
        return ""
