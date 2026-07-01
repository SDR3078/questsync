#!/usr/bin/env bash
# v1.1 dailys verification in DEMO mode. Demonstrates the materialized model:
# a "not due, not completed" daily is hidden; completing one flows to score/up.
set -uo pipefail

BASE="${BASE:-http://localhost:5232}"; U="${DAVUSER:-sander}"; P="${PASS:-x}"
COL="$BASE/$U/dailys/"
D1="d1111111-1111-1111-1111-111111111111"   # due, not done  -> shown
BODY="$(mktemp)"; trap 'rm -f "$BODY"' EXIT
req() { curl -s -u "$U:$P" -o "$BODY" -w "%{http_code}" "$@"; }
propfind() { req -X PROPFIND "$COL" -H 'Depth: 1' -H 'Content-Type: application/xml' \
  --data '<propfind xmlns="DAV:"><prop><getetag/></prop></propfind>'; }

echo "== dailys list — 'Weekly review' (not due) should be ABSENT =="
echo "  PROPFIND -> HTTP $(propfind)"
grep -o 'dailys/[^<]*\.ics' "$BODY" | sed 's/^/    /'

echo "== GET a due daily — DUE=today, X-HABITICA-TYPE:daily, streak =="
echo "  GET -> HTTP $(req "${COL}${D1}.ics")"
grep -E 'SUMMARY|STATUS|DUE|X-HABITICA' "$BODY" | sed 's/^/    /'

echo "== complete the daily via PUT (=> Habitica score/up) =="
echo "  PUT -> HTTP $(req -X PUT "${COL}${D1}.ics" -H 'Content-Type: text/calendar' --data "BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VTODO
UID:${D1}
DTSTAMP:20260701T120000Z
SUMMARY:Meditate
STATUS:COMPLETED
END:VTODO
END:VCALENDAR")"
echo "  GET -> HTTP $(req "${COL}${D1}.ics")"
grep -E 'STATUS|PERCENT-COMPLETE' "$BODY" | sed 's/^/    /'

echo
echo "Dailys demo checks done."
