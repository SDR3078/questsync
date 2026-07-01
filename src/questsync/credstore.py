"""Per-request credential bridge between the auth and storage plugins.

Radicale hands the DAV password (a user's Habitica API token) to Auth but not to
Storage. Since Radicale serves each request on a single thread (auth then storage
run on the same thread), we pass the token through THREAD-LOCAL storage: Auth
writes it, Storage reads it within the same request.

This keeps the token scoped to the in-flight request — at most one per worker
thread, overwritten on that thread's next request — so tokens are never logged,
never persisted, and never accumulate across users the way a process-global dict
would. (An earlier design evicted from a global dict at the end of acquire_lock,
but Radicale consumes discover() lazily *after* that context exits, so the token
had to outlive the lock; thread-local state does exactly that, safely.)
"""
import threading

_local = threading.local()


def put(user, token):
    _local.user = user
    _local.token = token


def get(user):
    if getattr(_local, "user", None) == user:
        return getattr(_local, "token", None)
    return None


def forget(user):
    if getattr(_local, "user", None) == user:
        _local.user = None
        _local.token = None
