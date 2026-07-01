# QuestSync

A **Habitica ⇄ Radicale (CalDAV)** bridge, delivered as a container, so Habitica
tasks are readable — and tickable — from any DAV-capable app (Tasks.org, Apple
Reminders, Nextcloud Tasks, Thunderbird, …).

## Architecture

QuestSync is a **custom Radicale `storage` backend, backed live by the Habitica
API** — *not* a separate service that replicates data into a stock Radicale.
Radicale becomes a **read-through / write-through façade** over Habitica:

- a DAV client `GET`/`REPORT` → the storage plugin fetches from Habitica and
  renders `VTODO`s on the fly;
- a DAV client `PUT`/`DELETE` → the plugin translates it into Habitica API calls.

There is **one source of truth (Habitica)**, so there is no second copy to
reconcile — no state store, no conflict resolution, no polling loop.

## Roadmap

1. **Prove** — validate the architecture with the thinnest possible slice.
   - ✅ *Prove-0:* stock Radicale in a container round-trips a task list.
   - ✅ *Prove-1:* a filesystem-free custom storage class serves a `VTODO` from code.
2. **Design** — read-through / write-through flow, mapping, identity, auth.
   **← current step** — see [`docs/design.md`](docs/design.md).
3. **Build** — wire the storage adapter to the Habitica API.

## Prove-0 — run it

```bash
docker compose up -d --build
bash scripts/prove0-verify.sh        # drives the full CalDAV path with curl
```

Or point a real DAV client at `http://<host>:5232/` (any username, any password
while `auth = none`) and watch the task appear.
