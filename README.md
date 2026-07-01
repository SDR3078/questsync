# QuestSync

A **Habitica ⇄ CalDAV** bridge: it makes Habitica tasks readable — and tickable —
from any DAV-capable app (Tasks.org, Apple Reminders, Nextcloud Tasks,
Thunderbird…) by exposing them through an embedded [Radicale](https://radicale.org)
CalDAV server.

**Multi-user:** one QuestSync instance serves many people. Each person logs in
with **their own Habitica User ID + API token** as their CalDAV credentials and
sees only their own tasks. The server stores no accounts.

## How it works

QuestSync is a custom Radicale **storage + auth plugin** — not a copy of your data:

- **Auth** (`radicale_auth.py`): DAV username = Habitica User ID, DAV password =
  Habitica API token, validated live against Habitica; the User ID becomes the
  DAV principal so `owner_only` rights isolate each user.
- **Storage** (`radicale_storage.py`): per request it fetches that user's tasks
  and renders them as `VTODO`s (read-through); a client `PUT`/`DELETE` is
  translated into Habitica API calls (write-through).
- One source of truth (Habitica) ⇒ no database, no sync conflicts, no state store.

Supported today: **todos** (full bidirectional) and **dailies** (materialized —
shown while due; completing one scores it). Habits/rewards are out of scope.

## Quick start (Docker)

```bash
git clone https://github.com/SDR3078/questsync && cd questsync
docker compose up -d --build
```

Add a CalDAV account in your app:

| Field | Value |
|-------|-------|
| Server / URL | `http://<host>:5232/` |
| Username | your **Habitica User ID** |
| Password | your **Habitica API Token** |

Both are at <https://habitica.com/user/settings/api>. You'll get two task lists:
**Habitica To-Dos** and **Habitica Dailies**.

> ⚠️ **Use HTTPS in production.** Credentials travel in HTTP Basic auth on every
> request — never expose QuestSync without TLS. See [Security](#security).

## Configuration (env)

| Var | Default | Meaning |
|-----|---------|---------|
| `QUESTSYNC_TASK_TYPES` | `todos,dailys` | Which lists to expose |
| `QUESTSYNC_CACHE_TTL` | `30` | Seconds to cache each user's task snapshot |
| `QUESTSYNC_LOGIN_TTL` | `300` | Seconds to trust a validated login before re-checking |
| `QUESTSYNC_CLIENT_AUTHOR` | *(user's id)* | Fixed `x-client` author id |
| `QUESTSYNC_DEMO` | *(off)* | `1` = offline fixture + accept any login (dev/CI) |

The server needs **no Habitica credentials of its own** — users bring theirs.

## Security

- **TLS is mandatory in production** — Basic-auth credentials (incl. the API
  token) are sent on every request.
- **Tokens are in-memory only:** validated against Habitica, cached in process,
  **never logged or persisted**. The login cache keys on a SHA-256 of the
  password, not the plaintext.
- **Isolation:** `owner_only` scopes each user to `/<their-id>/…`; cross-user
  access returns `403` (tested).
- **Trust model:** like any CalDAV bridge, the operator's server handles each
  user's token in memory while they're connected. Run it where you and your
  users trust the operator.

## Deploy to Kubernetes

See [`deploy/`](deploy/) for k8s + ArgoCD manifests. No app secret is required
(users bring their own creds); you only need a **TLS-terminating Ingress**.

## Development

```bash
# offline demo: fixture data, any login accepted
QUESTSYNC_DEMO=1 docker compose up -d
bash scripts/build-verify.sh          # todos read+write
bash scripts/dailys-verify.sh         # dailies

# unit tests (converter + credstore)
docker run --rm -e PYTHONPATH=/app -v "$PWD/src:/app:ro" -v "$PWD/tests:/tests:ro" \
  python:3.12-slim sh -lc "pip install -q vobject python-dateutil pytest && pytest -q /tests"

# live checks against a real account (creds read from .env, never printed)
docker compose up -d && bash scripts/live-multiuser-verify.sh
```

## Roadmap
- ✅ Multi-user, bidirectional todos + dailies — live-verified.
- ✅ CI builds & publishes the image to GHCR.
- ⬜ Real subtasks (`RELATED-TO`), tag sync, per-request rate limiting.
