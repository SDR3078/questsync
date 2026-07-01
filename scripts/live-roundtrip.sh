#!/usr/bin/env bash
# SAFE write round-trip against your REAL account: creates a clearly-labeled
# throwaway todo, completes it (=> Habitica score/up), then DELETES it.
# Net effect on your task list: nothing (you keep the tiny XP/gold from scoring).
set -uo pipefail

BASE="${BASE:-http://localhost:5232}"; U="${DAVUSER:-sander}"; P="${PASS:-x}"
COL="$BASE/$U/todos/"; STEM="questsync-livetest"
BODY="$(mktemp)"; trap 'rm -f "$BODY"' EXIT
req() { curl -s -u "$U:$P" -o "$BODY" -w "%{http_code}" "$@"; }

echo "== 1. CREATE a labeled test todo (=> POST /tasks/user) =="
echo "  PUT -> HTTP $(req -X PUT "${COL}${STEM}.ics" -H 'Content-Type: text/calendar' --data "BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//questsync//livetest//EN
BEGIN:VTODO
UID:${STEM}
DTSTAMP:20260701T120000Z
SUMMARY:QuestSync live test (safe to delete)
STATUS:NEEDS-ACTION
END:VTODO
END:VCALENDAR")"

echo "== 2. COMPLETE it (=> POST /tasks/:id/score/up) =="
echo "  PUT -> HTTP $(req -X PUT "${COL}${STEM}.ics" -H 'Content-Type: text/calendar' --data "BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//questsync//livetest//EN
BEGIN:VTODO
UID:${STEM}
DTSTAMP:20260701T120000Z
SUMMARY:QuestSync live test (safe to delete)
STATUS:COMPLETED
END:VTODO
END:VCALENDAR")"
echo "  GET -> HTTP $(req "${COL}${STEM}.ics")"
grep -E 'STATUS|PERCENT-COMPLETE' "$BODY" | sed 's/^/    /'

echo "== 3. DELETE it — cleanup (=> DELETE /tasks/:id) =="
echo "  DELETE -> HTTP $(req -X DELETE "${COL}${STEM}.ics")"
echo "  GET after delete (expect 404) -> HTTP $(req "${COL}${STEM}.ics")"
echo
echo "Round-trip done. Check Habitica: the test todo should be gone."
