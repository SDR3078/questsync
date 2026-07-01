"""Minimal Habitica API v3 client for QuestSync (todos + dailies).

Real mode talks to https://habitica.com/api/v3 with the three required headers
(x-api-user, x-api-key, x-client). `demo=True` serves an in-memory fixture so the
plugin and full DAV flow work without any real account.
"""
import time

import requests

DEFAULT_BASE_URL = "https://habitica.com/api/v3"

# Radicale collection id -> Habitica ?type= query value (note: "dailys" misspelled).
_LIST_QUERY = {"todos": "todos", "dailys": "dailys"}


def _demo_fixture():
    return [
        {"_id": "11111111-1111-1111-1111-111111111111", "type": "todo",
         "text": "Buy milk", "notes": "2% please", "completed": False,
         "date": "2026-07-05T00:00:00.000Z", "priority": 1, "checklist": [],
         "tags": [], "createdAt": "2026-06-30T09:00:00.000Z",
         "updatedAt": "2026-06-30T09:00:00.000Z"},
        {"_id": "22222222-2222-2222-2222-222222222222", "type": "todo",
         "text": "Ship QuestSync v1", "notes": "Habitica <-> Radicale bridge",
         "completed": False, "date": None, "priority": 2,
         "checklist": [{"id": "c1", "text": "read path", "completed": True},
                       {"id": "c2", "text": "write path", "completed": False}],
         "tags": [], "createdAt": "2026-06-29T12:00:00.000Z",
         "updatedAt": "2026-07-01T07:00:00.000Z"},
        {"_id": "33333333-3333-3333-3333-333333333333", "type": "todo",
         "text": "Water the plants", "notes": "", "completed": True,
         "date": None, "priority": 0.1, "checklist": [], "tags": [],
         "dateCompleted": "2026-06-30T18:00:00.000Z",
         "createdAt": "2026-06-28T08:00:00.000Z",
         "updatedAt": "2026-06-30T18:00:00.000Z"},
        {"_id": "d1111111-1111-1111-1111-111111111111", "type": "daily",
         "text": "Meditate", "notes": "10 minutes", "completed": False,
         "isDue": True, "nextDue": ["2026-07-01T00:00:00.000Z"],
         "frequency": "weekly", "everyX": 1, "streak": 5, "priority": 1,
         "checklist": [], "tags": [], "createdAt": "2026-05-01T00:00:00.000Z",
         "updatedAt": "2026-07-01T06:00:00.000Z"},
        {"_id": "d2222222-2222-2222-2222-222222222222", "type": "daily",
         "text": "Floss", "notes": "", "completed": True, "isDue": True,
         "nextDue": ["2026-07-01T00:00:00.000Z"], "priority": 0.1, "streak": 20,
         "checklist": [], "tags": [], "createdAt": "2026-05-01T00:00:00.000Z",
         "updatedAt": "2026-07-01T07:30:00.000Z"},
        {"_id": "d3333333-3333-3333-3333-333333333333", "type": "daily",
         "text": "Weekly review", "notes": "", "completed": False,
         "isDue": False, "nextDue": ["2026-07-05T00:00:00.000Z"], "priority": 1,
         "checklist": [], "tags": [], "createdAt": "2026-05-01T00:00:00.000Z",
         "updatedAt": "2026-06-28T09:00:00.000Z"},
    ]


_demo_store = None


def _shared_demo_store():
    """Process-wide demo fixture, shared across (request-scoped) demo clients so
    demo writes persist even though real clients are rebuilt per request."""
    global _demo_store
    if _demo_store is None:
        _demo_store = {t["_id"]: t for t in _demo_fixture()}
    return _demo_store


class HabiticaError(RuntimeError):
    pass


class HabiticaRateLimited(HabiticaError):
    """Raised on HTTP 429 — a rate limit, NOT an invalid credential."""


class HabiticaClient:
    def __init__(self, user_id="", api_token="", client_header="",
                 base_url=DEFAULT_BASE_URL, demo=False, max_retries=3):
        self.base_url = base_url.rstrip("/")
        self.demo = demo
        self._max_retries = max_retries
        if demo:
            self._fixture = _shared_demo_store()
        else:
            self._session = requests.Session()
            self._session.headers.update({
                "x-api-user": user_id, "x-api-key": api_token,
                "x-client": client_header or ("%s-questsync" % user_id),
                "content-type": "application/json"})

    def validate(self):
        """True iff these credentials authenticate; re-raises on rate limit."""
        if self.demo:
            return True
        try:
            self._request("GET", "/user", params={"userFields": "_id"})
            return True
        except HabiticaRateLimited:
            raise                      # transient: do NOT report as invalid
        except HabiticaError:
            return False

    # ---- HTTP with retry/backoff (honors 429 Retry-After) ---------------
    def _request(self, method, path, **kwargs):
        url = self.base_url + path
        resp = None
        for attempt in range(self._max_retries + 1):
            resp = self._session.request(method, url, timeout=30, **kwargs)
            if resp.status_code == 429 and attempt < self._max_retries:
                time.sleep(min(float(resp.headers.get("Retry-After", "2")), 60))
                continue
            if resp.status_code >= 500 and attempt < self._max_retries:
                time.sleep(2 ** attempt)
                continue
            break
        if resp.status_code == 429:
            raise HabiticaRateLimited("rate limited: %s %s" % (method, path))
        if not resp.ok:
            raise HabiticaError("%s %s -> %s" % (method, path, resp.status_code))
        body = resp.json()
        if not body.get("success", True):
            raise HabiticaError(str(body.get("message") or "request failed"))
        return body.get("data")

    # ---- task operations (collection id = "todos" | "dailys") -----------
    def list_tasks(self, collection_id):
        if self.demo:
            want = "todo" if collection_id == "todos" else "daily"
            return [dict(t) for t in self._fixture.values() if t["type"] == want]
        query = _LIST_QUERY.get(collection_id, collection_id)
        tasks = self._request("GET", "/tasks/user", params={"type": query}) or []
        if collection_id == "todos":
            tasks += self._request("GET", "/tasks/user",
                                    params={"type": "completedTodos"}) or []
        return tasks

    def get_task(self, id_or_alias):
        if self.demo:
            t = self._fixture.get(id_or_alias) or self._by_alias(id_or_alias)
            return dict(t) if t else None
        return self._request("GET", "/tasks/user/%s" % id_or_alias)

    def create_task(self, task_type, fields, alias=None):
        payload = dict(fields, type=task_type)
        if alias:
            payload["alias"] = alias
        if self.demo:
            new_id = alias or ("demo-%d" % (len(self._fixture) + 1))
            t = dict(payload, _id=new_id, completed=False, checklist=[],
                     tags=[], createdAt="2026-07-01T00:00:00.000Z",
                     updatedAt="2026-07-01T00:00:00.000Z")
            self._fixture[new_id] = t
            return dict(t)
        return self._request("POST", "/tasks/user", json=payload)

    def update_task(self, task_id, fields):
        if self.demo:
            t = self._fixture[task_id]
            t.update(fields)
            return dict(t)
        return self._request("PUT", "/tasks/%s" % task_id, json=fields)

    def score(self, task_id, direction):
        if self.demo:
            self._fixture[task_id]["completed"] = (direction == "up")
            return
        self._request("POST", "/tasks/%s/score/%s" % (task_id, direction))

    def delete_task(self, task_id):
        if self.demo:
            self._fixture.pop(task_id, None)
            return
        self._request("DELETE", "/tasks/%s" % task_id)

    def _by_alias(self, alias):
        for t in self._fixture.values():
            if t.get("alias") == alias:
                return t
        return None
