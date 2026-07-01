#!/usr/bin/env bash
# READ-ONLY live smoke test against your REAL Habitica account. Makes NO writes.
# Lists your real todos/dailys and shows how the first todo renders as a VTODO —
# the key check that live Habitica JSON converts correctly.
set -uo pipefail

BASE="${BASE:-http://localhost:5232}"; U="${DAVUSER:-sander}"; P="${PASS:-x}"
BODY="$(mktemp)"; trap 'rm -f "$BODY"' EXIT
req() { curl -s -u "$U:$P" -o "$BODY" -w "%{http_code}" "$@"; }
propfind() { req -X PROPFIND "$BASE/$U/$1/" -H 'Depth: 1' -H 'Content-Type: application/xml' \
  --data '<propfind xmlns="DAV:"><prop><getetag/></prop></propfind>'; }

echo "== READ-ONLY — nothing is written to your account =="

echo "== your real TODOS =="
echo "  PROPFIND -> HTTP $(propfind todos)   (500 => check creds; see: docker compose logs)"
todos=$(grep -o 'todos/[^<]*\.ics' "$BODY" || true)
echo "$todos" | sed 's/^/    /'
first=$(echo "$todos" | head -1)

echo "== your real DAILYS =="
echo "  PROPFIND -> HTTP $(propfind dailys)"
grep -o 'dailys/[^<]*\.ics' "$BODY" | sed 's/^/    /' || true

if [ -n "$first" ]; then
  echo "== GET first todo — how your REAL task renders as VTODO =="
  echo "  GET -> HTTP $(req "$BASE/$U/$first")"
  sed 's/^/    /' "$BODY"
else
  echo "  (no active todos to sample — add one in Habitica and re-run)"
fi
echo
echo "If the VTODO above looks correct, the live READ path works."
