"""QuestSync — a Radicale storage backend backed live by the Habitica API.

Reads Habitica tasks on demand and renders them as VTODOs; a client PUT/DELETE is
translated into Habitica API calls. One source of truth (Habitica) => no state
store. See docs/design.md.

Collection layout:
    ""              root
    "<user>"        principal home
    "<user>/todos"  the To-Dos task list
    "<user>/dailys" the Dailies task list (materialized "reappear" model)
"""
import contextlib
import os
import threading
import time

from radicale import item as radicale_item
from radicale.storage import BaseStorage, BaseCollection

from questsync import convert
from questsync.habitica import HabiticaClient

HTTP_DT = "%a, %d %b %Y %H:%M:%S GMT"
_DISPLAY = {"todos": "Habitica To-Dos", "dailys": "Habitica Dailies"}
_SINGULAR = {"todos": "todo", "dailys": "daily"}


def _parts(path):
    return [p for p in path.strip("/").split("/") if p]


def _now_http():
    return time.strftime(HTTP_DT, time.gmtime())


class Collection(BaseCollection):
    def __init__(self, storage, path):
        self._storage = storage
        self._path = path.strip("/")

    @property
    def path(self):
        return self._path

    def _coll_id(self):
        p = _parts(self._path)
        return p[1] if len(p) == 2 else None

    @property
    def last_modified(self):
        return _now_http()

    # --- read path --------------------------------------------------------
    def _items(self):
        cid = self._coll_id()
        if cid not in self._storage.collection_ids:
            return []
        out = []
        for task in self._storage.tasks(cid):
            if cid == "dailys":
                if not convert.daily_should_render(task):
                    continue
                text = convert.daily_to_ics(task)
            else:
                text = convert.todo_to_ics(task)
            href = (task.get("alias") or task["_id"]) + ".ics"
            out.append(radicale_item.Item(
                collection=self, href=href, text=text, last_modified=_now_http()))
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
        cid = self._coll_id()
        stem = href[:-4] if href.endswith(".ics") else href
        fields, completed = convert.ics_to_habitica(item.vobject_item.vtodo)
        client = self._storage.client
        existing = self._storage.find_task(cid, stem)

        if existing is None:                       # client-created task
            task = client.create_task(_SINGULAR.get(cid, "todo"), fields,
                                      alias=convert.safe_alias(stem))
            if completed:
                client.score(task["_id"], "up")
        else:                                      # edit / (un)complete
            task = client.update_task(existing["_id"], fields)
            if completed and not existing.get("completed"):
                client.score(existing["_id"], "up")
            elif not completed and existing.get("completed"):
                client.score(existing["_id"], "down")
        task["completed"] = completed
        self._storage.invalidate(cid)

        text = convert.daily_to_ics(task) if cid == "dailys" else convert.todo_to_ics(task)
        return radicale_item.Item(collection=self, href=href, text=text,
                                  last_modified=_now_http()), None

    def delete(self, href=None):
        cid = self._coll_id()
        if href is None:
            return                                 # synthetic collection: no-op
        stem = href[:-4] if href.endswith(".ics") else href
        existing = self._storage.find_task(cid, stem)
        if existing is not None:
            self._storage.client.delete_task(existing["_id"])
            self._storage.invalidate(cid)

    def set_meta(self, props):
        pass                                       # metadata is fixed; ignore


class Storage(BaseStorage):
    def __init__(self, configuration):
        super().__init__(configuration)
        self._lock = threading.RLock()
        self.client = HabiticaClient.from_env()
        self.collection_ids = [t.strip() for t in
                               os.environ.get("QUESTSYNC_TASK_TYPES", "todos,dailys")
                               .split(",") if t.strip()]
        self._ttl = float(os.environ.get("QUESTSYNC_CACHE_TTL", "30"))
        self._cache = {}                           # cid -> (tasks, monotonic_at)

    # cache (rate-limit friendly; refreshed within acquire_lock) -----------
    def tasks(self, cid):
        now = time.monotonic()
        cached = self._cache.get(cid)
        if cached is None or (now - cached[1]) > self._ttl:
            data = self.client.list_tasks(cid)
            self._cache[cid] = (data, now)
            return data
        return cached[0]

    def invalidate(self, cid=None):
        if cid is None:
            self._cache.clear()
        else:
            self._cache.pop(cid, None)

    def find_task(self, cid, id_or_alias):
        for t in self.tasks(cid):
            if t.get("_id") == id_or_alias or t.get("alias") == id_or_alias:
                return t
        return None

    # discover -------------------------------------------------------------
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
        if len(parts) == 1:                        # principal -> task lists
            for cid in self.collection_ids:
                yield Collection(self, parts[0] + "/" + cid)
        elif len(parts) == 2:                      # task list -> items
            yield from coll.get_all()

    def move(self, item, to_collection, to_href):
        raise NotImplementedError

    def create_collection(self, href, items=None, props=None):
        return Collection(self, href), {}, []

    @contextlib.contextmanager
    def acquire_lock(self, mode, user="", *args, **kwargs):
        with self._lock:
            yield

    def verify(self):
        return True
