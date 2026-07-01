#!/usr/bin/env bash
# Prove-1: our custom storage backend serves one hardcoded VTODO with NO client
# writes (no MKCOL, no PUT). If the item shows up, architecture B is proven.
#
# Usage:  docker compose up -d   &&   bash scripts/prove1-verify.sh
set -uo pipefail

BASE="${BASE:-http://localhost:5232}"
DAVUSER="${DAVUSER:-sander}"
PASS="${PASS:-proof}"
COL="$BASE/$DAVUSER/tasks/"
ITEM="${COL}hello@questsync.ics"
BODY="$(mktemp)"
trap 'rm -f "$BODY"' EXIT

req() { curl -s -u "$DAVUSER:$PASS" -o "$BODY" -w "%{http_code}" "$@"; }

echo "== 1. web UI alive =="
curl -s -o /dev/null -w "  /.web/ -> HTTP %{http_code}\n" "$BASE/.web/"

echo "== 2. PROPFIND principal home (Depth 1) — should list the task list =="
echo "  -> HTTP $(req -X PROPFIND "$BASE/$DAVUSER/" -H 'Depth: 1' -H 'Content-Type: application/xml' \
  --data '<propfind xmlns="DAV:"><prop><displayname/><resourcetype/></prop></propfind>')"
grep -o 'href>[^<]*' "$BODY" | sed 's/^/    /'

echo "== 3. PROPFIND the task list (Depth 1) — should list our hardcoded item =="
echo "  -> HTTP $(req -X PROPFIND "$COL" -H 'Depth: 1' -H 'Content-Type: application/xml' \
  --data '<propfind xmlns="DAV:"><prop><getetag/></prop></propfind>')"
grep -o 'href>[^<]*' "$BODY" | sed 's/^/    /'

echo "== 4. GET the item — served entirely by the plugin, no prior PUT =="
echo "  -> HTTP $(req "$ITEM")"
sed 's/^/    /' "$BODY"

echo "== 5. calendar-query REPORT (VTODO filter) — what a DAV client pulls =="
echo "  -> HTTP $(req -X REPORT "$COL" -H 'Depth: 1' -H 'Content-Type: application/xml' \
  --data '<?xml version="1.0"?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
<D:prop><D:getetag/><C:calendar-data/></D:prop>
<C:filter><C:comp-filter name="VCALENDAR"><C:comp-filter name="VTODO"/></C:comp-filter></C:filter>
</C:calendar-query>')"
grep -o 'SUMMARY:[^<]*' "$BODY" | sed 's/^/    /' || echo "    (no SUMMARY)"

echo
echo "Prove-1 holds if the item appears in steps 3-5 with NO MKCOL and NO PUT."
