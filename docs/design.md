# QuestSync — Design

> Status: **Design** (Prove-0 and Prove-1 complete). This document is the plan
> we build against. Facts about the Habitica API and Radicale interface below
> are verified against the live API docs and Radicale 3.7.5 source.

## 1. Architecture (recap)

QuestSync is a **custom Radicale `storage` backend backed live by the Habitica
REST API** — a read-through / write-through **façade**, not a replica.

```
DAV client  ──CalDAV──▶  Radicale  ──plugin calls──▶  QuestSync Storage  ──HTTPS──▶  Habitica API
   (Tasks.org, …)         (core)      get_all/upload/…     (this repo)      /api/v3     (source of truth)
```

One source of truth (Habitica) ⇒ **no state store, no merge base, no conflict
resolution, no polling loop.** Reads happen on demand when a client syncs.

## 2. Collection layout

One Radicale collection per Habitica task type we expose, each advertised as a
**VTODO** calendar (`get_meta`: `tag=VCALENDAR`,
`supported-calendar-component-set=VTODO`):

| Path | Source | Notes |
|------|--------|-------|
| `/<user>/todos/`  | Habitica `?type=todos` (+ optionally last-30 `completedTodos`) | The clean case. |
| `/<user>/dailys/` | Habitica `?type=dailys`, **materialized** (see §5) | Recurrence handled by us, not RRULE. |
| ~~habits~~ / ~~rewards~~ | excluded | No completion semantics / not tasks. |

`discover()` synthesizes these collections in code (as Prove-1 already does), so
the "child collection isn't auto-created" problem that bites the replica model
**does not exist here** — the lists simply *are*.

## 3. Identity — derived, no store

- **Resource href:** `<id>.ics`  where `<id>` = the Habitica task `alias` if set,
  else its `_id` (a UUID).
- **VTODO `UID`:** the same `<id>`.

Correlation is *computed*, never remembered. Given a Habitica task we know its
href; given an href we recover the task by `GET /tasks/user/:idOrAlias`.

**Client-created tasks (bidirectional):** when a DAV client `PUT`s a brand-new
VTODO, `upload()` creates it in Habitica with **`alias` = the client's chosen
href-stem** (Habitica natively supports a unique per-user `alias`, charset
`[A-Za-z0-9_-]`). That binds the two identities *inside Habitica* — still no
state store. Caveat: if the client's UID isn't alias-safe (e.g. contains `@`),
we sanitize it; edge handling tracked in §7.

## 4. The mapping — Habitica ⇄ VTODO

### Read (Habitica task → VTODO)

| VTODO property | From Habitica | Notes |
|----------------|---------------|-------|
| `UID` / href | `alias` or `_id` | §3 |
| `SUMMARY` | `text` | title |
| `DESCRIPTION` | `notes` (+ checklist, see below) | |
| `DUE` | `date` (todos) / today from `nextDue` (dailys) | `VALUE=DATE` for date-only |
| `STATUS` | `completed` | `true`→`COMPLETED`, `false`→`NEEDS-ACTION` |
| `COMPLETED` | `dateCompleted` | only when done |
| `PERCENT-COMPLETE` | `completed` | `100` when done |
| `PRIORITY` | `priority` (difficulty) | **lossy** — see below |
| `CATEGORIES` | `tags` (resolved via `GET /tags`) | deferred in v1 (UUID→name costs a call) |
| `CREATED` | `createdAt` | |
| `LAST-MODIFIED` | `updatedAt` | also drives the ETag |
| `DTSTAMP` | now | required |
| `X-HABITICA-*` | `priority`, `type`, `streak`, … | **lossless round-trip** of Habitica-only fields |

**`priority` is difficulty, not urgency** (`0.1/1/1.5/2` = trivial/easy/medium/
hard). VTODO has no "difficulty" slot, so we approximate into `PRIORITY`
(hard→1, medium→5, easy→6, trivial→9) *and* keep the raw value in
`X-HABITICA-PRIORITY` so a client edit that doesn't touch priority round-trips
exactly.

**Checklists** (`checklist: [{id,text,completed}]`): v1 renders them as lines in
`DESCRIPTION` (read-mostly). v2 upgrades to real subtasks via
`RELATED-TO;RELTYPE=PARENT` child VTODOs once we've confirmed client support.

### Write (VTODO `PUT`/`DELETE` → Habitica)

| Client action | Habitica call |
|---------------|---------------|
| `PUT` to a **known** href (existing `_id`/alias) | `PUT /tasks/:id` for text/notes/date/priority changes |
| …and `STATUS` flipped to `COMPLETED` | `POST /tasks/:id/score/up` |
| …and `STATUS` flipped back to `NEEDS-ACTION` | `POST /tasks/:id/score/down` |
| `PUT` to a **new** href | `POST /tasks/user` with `alias=<href-stem>` (§3) |
| `DELETE` | `DELETE /tasks/:id` |

Scoring (`score/up`) returns *stats*, not the task, so after a write we
invalidate the cache and re-read on the next request.

## 5. Dailies — materialized, not RRULE

Recurring VTODOs are poorly supported across clients, so QuestSync **owns the
schedule** and renders Habitica's *current* state (the "let it reappear" model):

- Show a daily as a plain (non-recurring) VTODO **only when Habitica says it's
  due and not done** (`isDue == true && completed == false`); `DUE` = today.
- When `completed == true` or not due → present as `STATUS:COMPLETED` (or omit).
- Tomorrow Habitica's cron resets `completed` → it reappears automatically.

No `RRULE`, no occurrence bookkeeping. Habitica is the schedule source of truth.

## 6. Request flow & rate limits

Every request passes through `acquire_lock(mode, user)` — our fetch/flush
boundary:

- **On entry:** ensure a fresh-enough Habitica snapshot. Habitica's limit is
  **30 requests / 60 s** (`X-RateLimit-*` headers; `429` + `Retry-After`), so we
  cache the task list for a short **TTL (default ~30 s)** and serve all reads in
  a sync burst from cache. This is a *cache*, not a state store.
- **`sync()`** is intentionally **not overridden** → Radicale's default forces a
  client full-resync (legal per RFC 6578), correct for a backend with no delta
  feed.
- Wrap the Habitica client in retry/backoff honoring `Retry-After`.

## 7. Auth & config (v1 = single-user)

QuestSync syncs **one** Habitica account, so credentials live in the container
env, and DAV auth is just a gate:

| Env var | Purpose |
|---------|---------|
| `HABITICA_USER_ID` | `x-api-user` header |
| `HABITICA_API_TOKEN` | `x-api-key` header (password-equivalent) |
| `HABITICA_CLIENT` | `x-client` header; default `${HABITICA_USER_ID}-questsync` (mandatory since 2025-07) |
| `QUESTSYNC_TASK_TYPES` | `todos` or `todos,dailys` |
| `QUESTSYNC_CACHE_TTL` | seconds (default 30) |
| `QUESTSYNC_DAV_*` | DAV Basic-auth gate (htpasswd or reuse) |

The plugin reads these from the environment (container-idiomatic), sidestepping
Radicale's config schema. A custom `BaseAuth` is optional in v1 (single user); it
becomes necessary only for multi-user, where the DAV password would carry the
Habitica token and the storage would key clients by user.

Open edges to resolve during Build:
- alias-safety of client-chosen UIDs (§3).
- tags resolution cost (§4) — batch `GET /tags` once per snapshot.
- cron-bumped `updatedAt` looking like a spurious edit (only matters if we ever
  add change-detection; the façade doesn't, so parked).

## 8. What Build actually changes

Everything structural is done (Prove-1). Build =
1. a `HabiticaClient` (auth headers, endpoints, retry) — new,
2. a `task ⇄ vtodo` converter (§4) — new,
3. rewrite `Collection.get_all`/`get_multi` to read via the client + cache,
4. implement `Collection.upload`/`delete` per §4,
5. read config from env; keep `discover`, `acquire_lock`, `get_meta` as-is.
