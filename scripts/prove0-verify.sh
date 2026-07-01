#!/usr/bin/env bash
# Prove-0 verification: a stock Radicale can hold a VTODO task list that a DAV
# client reads back. Drives the full CalDAV path with curl — no app required.
#
# Usage:  docker compose up -d --build   &&   bash scripts/prove0-verify.sh
set -uo pipefail

BASE="${BASE:-http://localhost:5232}"
DAVUSER="${DAVUSER:-sander}"
PASS="${PASS:-proof}"                 # [auth] type=none accepts any password
COL="$BASE/$DAVUSER/tasks/"
BODY="$(mktemp)"
trap 'rm -f "$BODY"' EXIT

req() { curl -s -u "$DAVUSER:$PASS" -o "$BODY" -w "%{http_code}" "$@"; }

echo "== 1. web UI alive =="
curl -s -o /dev/null -w "  GET /.web/  -> HTTP %{http_code}\n" "$BASE/.web/"

echo "== 2. PROPFIND principal (expect 207) =="
echo "  -> HTTP $(req -X PROPFIND "$BASE/" -H 'Depth: 0' -H 'Content-Type: application/xml' \
  --data '<propfind xmlns="DAV:"><prop><current-user-principal/></prop></propfind>')"

echo "== 3. MKCOL a VTODO task list (expect 201; 405/409 on re-run = already exists) =="
echo "  -> HTTP $(req -X MKCOL "$COL" -H 'Content-Type: application/xml' --data '<?xml version="1.0" encoding="utf-8"?>
<mkcol xmlns="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav"><set><prop>
<resourcetype><collection/><C:calendar/></resourcetype>
<displayname>QuestSync Tasks</displayname>
<C:supported-calendar-component-set><C:comp name="VTODO"/></C:supported-calendar-component-set>
</prop></set></mkcol>')"

echo "== 4. PUT one VTODO (expect 201) =="
echo "  -> HTTP $(req -X PUT "${COL}proof.ics" -H 'Content-Type: text/calendar' --data 'BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//questsync//prove0//EN
BEGIN:VTODO
UID:proof@questsync
DTSTAMP:20260701T000000Z
SUMMARY:Prove-0 works
STATUS:NEEDS-ACTION
END:VTODO
END:VCALENDAR')"

echo "== 5. GET it back (expect 200) =="
echo "  -> HTTP $(req "${COL}proof.ics")"
sed 's/^/    /' "$BODY"

echo "== 6. calendar-query REPORT — what a DAV client pulls (expect 207) =="
echo "  -> HTTP $(req -X REPORT "$COL" -H 'Depth: 1' -H 'Content-Type: application/xml' --data '<?xml version="1.0"?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
<D:prop><D:getetag/><C:calendar-data/></D:prop>
<C:filter><C:comp-filter name="VCALENDAR"><C:comp-filter name="VTODO"/></C:comp-filter></C:filter>
</C:calendar-query>')"
echo "  SUMMARY found in report payload:"
grep -o 'SUMMARY:[^<]*' "$BODY" | sed 's/^/    /' || echo "    (none — check the steps above)"

echo
echo "Baseline holds if steps 2-6 are 2xx and steps 5/6 show 'Prove-0 works'."
