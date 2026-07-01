"""In-process bridge between the auth plugin and the storage plugin.

Radicale hands the DAV password (a user's Habitica API token) to the Auth plugin,
but Storage only ever receives the *username*. Auth validates the token and
stashes it here keyed by user; Storage reads it to build that user's Habitica
client. Tokens live ONLY in memory for the process lifetime — never logged,
never written to disk.
"""
import threading

_lock = threading.Lock()
_tokens = {}


def put(user, token):
    with _lock:
        _tokens[user] = token


def get(user):
    with _lock:
        return _tokens.get(user)


def forget(user):
    with _lock:
        _tokens.pop(user, None)
