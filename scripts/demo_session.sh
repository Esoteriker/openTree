#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8101}"

SESSION_ID=$(curl -s -X POST "$BASE_URL/v1/sessions" \
  -H 'content-type: application/json' \
  -d '{"user_id":"demo-user","metadata":{"source":"demo-script"}}' | \
  python3 -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')

echo "session_id=$SESSION_ID"

echo "[1/2] sending first turn"
curl -s -X POST "$BASE_URL/v1/sessions/$SESSION_ID/turns" \
  -H 'content-type: application/json' \
  -d '{"speaker":"user","content":"Graph Neural Networks can improve relation inference because they propagate structure."}'

echo

echo "[2/2] sending follow-up turn"
curl -s -X POST "$BASE_URL/v1/sessions/$SESSION_ID/turns" \
  -H 'content-type: application/json' \
  -d '{"speaker":"assistant","content":"This method depends on clean concept extraction before graph updates."}'

echo

echo "done"
