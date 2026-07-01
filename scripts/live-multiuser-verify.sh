#!/usr/bin/env bash
# Live MULTI-USER verify: authenticate with YOUR real Habitica creds (read from
# .env) as DAV credentials. Confirms real reads work, bad creds are rejected,
# and users are isolated. Reads .env but never prints the token.
#
#   docker compose up -d   &&   bash scripts/live-multiuser-verify.sh
set -uo pipefail

[ -f .env ] || { echo ".env not found"; exit 1; }
set -a; . ./.env; set +a
U="${HABITICA_USER_ID:-}"; P="${HABITICA_API_TOKEN:-}"
[ -n "$U" ] && [ -n "$P" ] || { echo "HABITICA_USER_ID / _API_TOKEN missing in .env"; exit 1; }
BASE="${BASE:-http://localhost:5232}"
BODY="$(mktemp)"; trap 'rm -f "$BODY"' EXIT

echo "== no credentials  -> expect 401 =="
echo "  HTTP $(curl -s -o /dev/null -w '%{http_code}' -X PROPFIND "$BASE/$U/todos/" -H 'Depth: 0')"

echo "== wrong token     -> expect 401 =="
echo "  HTTP $(curl -s -o /dev/null -w '%{http_code}' -u "$U:definitely-wrong-token" -X PROPFIND "$BASE/$U/todos/" -H 'Depth: 0')"

echo "== YOUR creds      -> expect 207 + your real todos =="
code=$(curl -s -u "$U:$P" -o "$BODY" -w '%{http_code}' -X PROPFIND "$BASE/$U/todos/" -H 'Depth: 1' -H 'Content-Type: application/xml' --data '<propfind xmlns="DAV:"><prop><getetag/></prop></propfind>')
echo "  HTTP $code   todos found: $(grep -o 'todos/[^<]*\.ics' "$BODY" | wc -l)"

echo "== isolation: another user's path with YOUR creds -> expect 403 =="
echo "  HTTP $(curl -s -o /dev/null -w '%{http_code}' -u "$U:$P" -X PROPFIND "$BASE/00000000-0000-0000-0000-000000000000/todos/" -H 'Depth: 0')"

echo
echo "Multi-user live checks done (401 / 401 / 207 / 403 = all correct)."
