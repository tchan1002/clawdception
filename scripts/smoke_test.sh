#!/bin/bash
# smoke_test.sh — verify all Media Luna API endpoints are responding correctly
# Run after any change to sensor_server.py (post-restart)
#
# Usage:
#   bash scripts/smoke_test.sh
#   bash scripts/smoke_test.sh http://192.168.12.76:5001   # target Pi from laptop

BASE="${1:-http://localhost:5001}"
PASS=0
FAIL=0

check() {
    local desc="$1"
    local expected_status="$2"
    local url="$3"
    local method="${4:-GET}"
    local data="$5"

    if [ "$method" = "POST" ]; then
        actual=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
            -H "Content-Type: application/json" \
            -d "$data" "$url")
    else
        actual=$(curl -s -o /dev/null -w "%{http_code}" "$url")
    fi

    if [ "$actual" = "$expected_status" ]; then
        echo "  PASS  $desc ($actual)"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  $desc — expected $expected_status, got $actual"
        FAIL=$((FAIL + 1))
    fi
}

check_json() {
    local desc="$1"
    local url="$2"
    local key="$3"

    body=$(curl -s "$url")
    if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert '$key' in d" 2>/dev/null; then
        echo "  PASS  $desc (has '$key')"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  $desc — key '$key' missing. Response: $body"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "=== Media Luna Smoke Test ==="
echo "Target: $BASE"
echo ""

echo "--- Core pages ---"
check "Dashboard (GET /)" 200 "$BASE/"
check "Water test UI (GET /water-test)" 200 "$BASE/water-test"
check "Agent status UI (GET /agent)" 200 "$BASE/agent"

echo ""
echo "--- Sensor API ---"
check "Health check" 200 "$BASE/api/health"
check_json "Health has 'status'" "$BASE/api/health" "status"
check "Latest reading" 200 "$BASE/api/sensors/latest"
check "Recent readings (default)" 200 "$BASE/api/sensors"
check "Recent readings (limit)" 200 "$BASE/api/sensors?limit=5"
check "Recent readings (hours)" 200 "$BASE/api/sensors?hours=24"

echo ""
echo "--- Events API ---"
check "Get events" 200 "$BASE/api/events"
check "Get events (type filter)" 200 "$BASE/api/events?type=water_test"
check "Get events (since filter)" 200 "$BASE/api/events?since=2026-01-01T00:00:00"
check "Post event (valid)" 201 "$BASE/api/events" POST \
    '{"event_type":"smoke_test","data":{"note":"automated smoke test"},"source":"agent"}'
check "Post event (missing event_type)" 400 "$BASE/api/events" POST '{}'
check "Post sensor (invalid JSON)" 400 "$BASE/api/sensors" POST 'not-json'

echo ""
echo "--- Journal API ---"
check "Journal (no date = most recent)" 200 "$BASE/api/journal"
check "Journal (valid date)" 200 "$BASE/api/journal?date=2026-04-01"
check "Journal (invalid date)" 400 "$BASE/api/journal?date=not-a-date"

echo ""
echo "=============================="
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
    echo "Some checks failed. Inspect server logs:"
    echo "  sudo journalctl -u media-luna.service -n 50"
    exit 1
else
    echo "All checks passed."
    exit 0
fi
