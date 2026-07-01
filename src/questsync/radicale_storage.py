"""QuestSync — a multi-user Radicale storage backend backed live by Habitica.

Each DAV principal `<user>` is a Habitica User ID (see radicale_auth.py). For a
request under `/<user>/...`, storage builds that user's HabiticaClient from the
token cached in `credstore` and serves only their tasks. `[rights] owner_only`
isolates each user. One source of truth (Habitica) => no state store.

Credentials are request-scoped via thread-local state (see credstore); each
HabiticaClient is built fresh per call so none pins a token past its request
(this also picks up a rotated token immediately). See docs/design.md.
"""
import contextlib
import os
import threading
import time

from radicale import item as radicale_item
from radicale.storage import BaseStorage, BaseCollection

from questsync import convert, credstore
from questsync.habitica import HabiticaClient
from questsync.settings import DEMO

_DISPLAY = {"todos": "Habitica To-Dos", "dailys": "Habitica Dailies"}
_SINGULAR = {"todos": "todo", "dailys": "daily"}


def _parts(path):
    return [p for p in path.strip("/").split("/") if p]


class Collection(BaseCollection):
    def __init__(self, storage, path):
        self._storage = storage
        self._path = path.strip("/")

    @property
    def path(self):
        return self._path

    def _user(self):
        p = _parts(self._path)
        return p[0] if p else None

    def _coll_id(self):
        p = _parts(self._path)
        return p[1] if len(p) >= 2 else None

    @property
    def last_modified(self):
        # Deterministic: newest task updatedAt, else epoch (never wall-clock).
        user, cid = self._user(), self._coll_id()
        if cid in self._storage.collection_ids:
            stamps = [t.get("updatedAt") for t in self._storage.tasks(user, cid)
                      if t.get("updatedAt")]
            return convert.http_date(max(stamps) if stamps else convert.EPOCH_ISO)
        return convert.http_date(convert.EPOCH_ISO)

    # --- read path --------------------------------------------------------
    def _items(self):
        user, cid = self._user(), self._coll_id()
        if cid not in self._storage.collection_ids:
            return []
        out = []
        for task in self._storage.tasks(user, cid):
            if cid == "dailys":
                if not convert.daily_should_render(task):
                    continue
                text = convert.daily_to_ics(task)
            else:
                text = convert.todo_to_ics(task)
            href = (task.get("alias") or task["_id"]) + ".ics"
            out.append(radicale_item.Item(
                collection=self, href=href, text=text,
                last_modified=convert.task_lastmod(task)))
        return out

    def get_all(self):
        return iter(self._items())

    def get_multi(self, hrefs):
        by_href = {i.href: i for i in self._items()}
        for href in hrefs:
            yield href, by_href.get(href)

    def get_meta(self, key=None):
        cid = self._coll_id()
        if cid in self._storage.collection_ids:
            meta = {"tag": "VCALENDAR",
                    "C:supported-calendar-component-set": "VTODO",
                    "D:displayname": _DISPLAY.get(cid, cid)}
        else:
            p = _parts(self._path)
            meta = {"D:displayname": p[-1] if p else "root"}
        return meta if key is None else meta.get(key)

    # --- write path -------------------------------------------------------
    def upload(self, href, item):
        user, cid = self._user(), self._coll_id()
        stem = href[:-4] if href.endswith(".ics") else href
        fields, completed = convert.ics_to_habitica(item.vobject_item.vtodo)
        client = self._storage.client_for(user)
        existing = self._storage.find_task(user, cid, stem)

        if existing is None:
            task = client.create_task(_SINGULAR.get(cid, "todo"), fields,
                                      alias=convert.safe_alias(stem))
            if completed:
                client.score(task["_id"], "up")
        else:
            task = client.update_task(existing["_id"], fields)
            if completed and not existing.get("completed"):
                client.score(existing["_id"], "up")
            elif not completed and existing.get("completed"):
                client.score(existing["_id"], "down")
        task["completed"] = completed
        self._storage.invalidate(user, cid)

        text = convert.daily_to_ics(task) if cid == "dailys" else convert.todo_to_ics(task)
        return radicale_item.Item(collection=self, href=href, text=text,
                                  last_modified=convert.task_lastmod(task)), None

    def delete(self, href=None):
        user, cid = self._user(), self._coll_id()
        if href is None:
            return
        stem = href[:-4] if href.endswith(".ics") else href
        existing = self._storage.find_task(user, cid, stem)
        if existing is not None:
            self._storage.client_for(user).delete_task(existing["_id"])
            self._storage.invalidate(user, cid)

    def set_meta(self, props):
        pass


class Storage(BaseStorage):
    def __init__(self, configuration):
        super().__init__(configuration)
        self._cache_lock = threading.Lock()       # guards self._cache only
        self._demo = DEMO
        self._base = os.environ.get("HABITICA_BASE_URL",
                                    "https://habitica.com/api/v3")
        self._author = os.environ.get("QUESTSYNC_CLIENT_AUTHOR", "")
        self.collection_ids = [t.strip() for t in
                               os.environ.get("QUESTSYNC_TASK_TYPES", "todos,dailys")
                               .split(",") if t.strip()]
        self._ttl = float(os.environ.get("QUESTSYNC_CACHE_TTL", "30"))
        self._cache = {}                           # (user, cid) -> (tasks, at)

    def _assert_owner(self, user):
        # Defense-in-depth: tenant isolation must not hang solely on the
        # owner_only rights config. The path's user must equal the authenticated
        # principal (thread-local) before we ever touch that user's data.
        authed = credstore.current_user()
        if authed is None or authed != user:
            raise RuntimeError("tenant isolation: path user %r != authenticated %r"
                               % (user, authed))

    def client_for(self, user):
        # Built fresh per call from the request's thread-local token, so a
        # rotated token is used immediately and no client pins one across requests.
        self._assert_owner(user)
        if self._demo:
            return HabiticaClient(user, demo=True)
        token = credstore.get(user)
        if not token:
            raise RuntimeError("no cached credentials for %r" % user)
        header = "%s-questsync" % (self._author or user)
        return HabiticaClient(user, token, client_header=header, base_url=self._base)

    def tasks(self, user, cid):
        self._assert_owner(user)
        key = (user, cid)
        now = time.monotonic()
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached is not None and (now - cached[1]) <= self._ttl:
                return cached[0]
        data = self.client_for(user).list_tasks(cid)   # network I/O — no lock held
        with self._cache_lock:
            self._cache[key] = (data, time.monotonic())
        return data

    def invalidate(self, user, cid=None):
        with self._cache_lock:
            for key in [k for k in self._cache if k[0] == user
                        and (cid is None or k[1] == cid)]:
                self._cache.pop(key, None)

    def find_task(self, user, cid, id_or_alias):
        for t in self.tasks(user, cid):
            if t.get("_id") == id_or_alias or t.get("alias") == id_or_alias:
                return t
        return None

    def discover(self, path, depth="0", child_context_manager=None,
                 user_groups=set()):
        parts = _parts(path)
        if parts and parts[-1].endswith(".ics"):
            coll = Collection(self, "/".join(parts[:-1]))
            for _href, item in coll.get_multi([parts[-1]]):
                if item is not None:
                    yield item
            return

        coll = Collection(self, "/".join(parts))
        yield coll
        if depth == "0":
            return
        if len(parts) == 1:
            for cid in self.collection_ids:
                yield Collection(self, parts[0] + "/" + cid)
        elif len(parts) == 2:
            yield from coll.get_all()

    def move(self, item, to_collection, to_href):
        raise NotImplementedError

    def create_collection(self, href, items=None, props=None):
        return Collection(self, href), {}, []

    @contextlib.contextmanager
    def acquire_lock(self, mode, user="", *args, **kwargs):
        # No global lock: the facade keeps no authoritative local state, so
        # tenants run concurrently (one slow Habitica call no longer stalls
        # everyone). The only shared mutable state — the task cache — is guarded
        # by a short lock in tasks()/invalidate(), never held across network I/O.
        yield

    def verify(self):
        return True
