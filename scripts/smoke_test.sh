#!/usr/bin/env bash
set -euo pipefail

ALB_DNS="${1:?Usage: smoke_test.sh <alb-dns-name>}"
BASE="http://${ALB_DNS}:8080"

echo "→ Frontend serves the login page"
curl -sf "http://${ALB_DNS}/login" | grep -q "Sign in to the BD Console"

echo "→ Health check"
curl -sf "${BASE}/health" | grep -q '"status":"ok"'

echo "→ Login as a customer"
LOGIN_RESP=$(curl -sf -X POST "${BASE}/auth/login" -H "Content-Type: application/json" \
  -d '{"name":"Smoke Test","email":"smoke@example.com"}')
TOKEN=$(echo "$LOGIN_RESP" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

echo "→ Submit a request"
curl -sf -X POST "${BASE}/requests" -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"brand":"Ozempic","market":"US"}' | grep -q '"status":"Awaiting assignment"'

echo "→ List requests, expect exactly one"
COUNT=$(curl -sf "${BASE}/requests" -H "Authorization: Bearer ${TOKEN}" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))')
[ "$COUNT" = "1" ]

echo "✓ Smoke test passed against ${BASE}"
