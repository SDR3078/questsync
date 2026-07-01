#!/usr/bin/env bash
# Build verification in DEMO mode (no Habitica creds): exercises the full read +
# write path through Radicale against the in-memory fixture.
#
#   docker compose up -d   &&   bash scripts/build-verify.sh
set -uo pipefail

BASE="${BASE:-http://localhost:5232}"; U="${DAVUSER:-sander}"; P="${PASS:-x}"
COL="$BASE/$U/todos/"
T1="11111111-1111-1111-1111-111111111111"
T3="33333333-3333-3333-3333-333333333333"
BODY="$(mktemp)"; trap 'rm -f "$BODY"' EXIT
req() { curl -s -u "$U:$P" -o "$BODY" -w "%{http_code}" "$@"; }
propfind() { req -X PROPFIND "$COL" -H 'Depth: 1' -H 'Content-Type: application/xml' \
  --data '<propfind xmlns="DAV:"><prop><getetag/></prop></propfind>'; }

echo "== READ: list todos (rendered from the fixture) =="
echo "  PROPFIND -> HTTP $(propfind)"
grep -o 'todos/[^<]*\.ics' "$BODY" | sed 's/^/    /'

echo "== READ: GET one todo — checklist->DESCRIPTION, difficulty->PRIORITY =="
echo "  GET -> HTTP $(req "${COL}22222222-2222-2222-2222-222222222222.ics")"
grep -E 'SUMMARY|STATUS|PRIORITY|X-HABITICA|DESCRIPTION' "$BODY" | sed 's/^/    /'

echo "== WRITE: mark '$T1' COMPLETED via PUT (=> Habitica score/up) =="
echo "  PUT -> HTTP $(req -X PUT "${COL}${T1}.ics" -H 'Content-Type: text/calendar' --data "BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VTODO
UID:${T1}
DTSTAMP:20260701T120000Z
SUMMARY:Buy milk
STATUS:COMPLETED
END:VTODO
END:VCALENDAR")"
echo "  GET  -> HTTP $(req "${COL}${T1}.ics")"
grep -E 'STATUS|PERCENT-COMPLETE' "$BODY" | sed 's/^/    /'

echo "== WRITE: create a client-born todo via PUT (=> Habitica create + alias) =="
echo "  PUT -> HTTP $(req -X PUT "${COL}from-phone.ics" -H 'Content-Type: text/calendar' --data 'BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VTODO
UID:from-phone
DTSTAMP:20260701T120000Z
SUMMARY:Task made on my phone
STATUS:NEEDS-ACTION
END:VTODO
END:VCALENDAR')"
echo "  list now -> HTTP $(propfind)"
grep -o 'todos/[^<]*\.ics' "$BODY" | sed 's/^/    /'

echo "== WRITE: delete '$T3' (=> Habitica delete) =="
echo "  DELETE -> HTTP $(req -X DELETE "${COL}${T3}.ics")"
echo "  list now -> HTTP $(propfind)"
grep -o 'todos/[^<]*\.ics' "$BODY" | sed 's/^/    /'

echo
echo "Build demo checks done."
