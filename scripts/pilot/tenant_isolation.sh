#!/usr/bin/env bash
set -euo pipefail

API_BASE=${API_BASE:-"http://localhost:8000"}
ADMIN_TOKEN=${ADMIN_TOKEN:-""}

if [[ -z "$ADMIN_TOKEN" ]]; then
  echo "ADMIN_TOKEN is required" >&2
  exit 1
fi

request() {
  local method=$1
  local path=$2
  local tenant=$3
  local payload=${4:-}

  if [[ -n "$payload" ]]; then
    curl -sS -X "$method" "${API_BASE}${path}" \
      -H "Authorization: Bearer ${ADMIN_TOKEN}" \
      -H "X-Tenant: ${tenant}" \
      -H "Content-Type: application/json" \
      -d "$payload"
  else
    curl -sS -X "$method" "${API_BASE}${path}" \
      -H "Authorization: Bearer ${ADMIN_TOKEN}" \
      -H "X-Tenant: ${tenant}" \
      -H "Content-Type: application/json"
  fi
}

extract_id() {
  python - <<'PY'
import json
import sys
payload = json.load(sys.stdin)
print(payload.get("id") or "")
PY
}

TENANT_A="pilot-a"
TENANT_B="pilot-b"

echo "Creating tenants..."
request POST "/api/v1/tenants" "$TENANT_A" '{"slug":"pilot-a","name":"Pilot A","contact_email":"pilot-a@example.com"}' > /tmp/tenant_a.json
request POST "/api/v1/tenants" "$TENANT_B" '{"slug":"pilot-b","name":"Pilot B","contact_email":"pilot-b@example.com"}' > /tmp/tenant_b.json

TENANT_A_ID=$(cat /tmp/tenant_a.json | extract_id)
TENANT_B_ID=$(cat /tmp/tenant_b.json | extract_id)

if [[ -z "$TENANT_A_ID" || -z "$TENANT_B_ID" ]]; then
  echo "Failed to create tenants." >&2
  exit 1
fi

echo "Creating company in tenant A..."
request POST "/api/v1/companies" "$TENANT_A" '{"name":"Pilot A Co"}' > /tmp/company_a.json
COMPANY_A_ID=$(cat /tmp/company_a.json | extract_id)

if [[ -z "$COMPANY_A_ID" ]]; then
  echo "Failed to create company for tenant A." >&2
  exit 1
fi

echo "Listing companies in tenant B (should be empty or not include tenant A)..."
request GET "/api/v1/companies" "$TENANT_B" | python - <<'PY'
import json
import sys
payload = json.load(sys.stdin)
items = payload.get("items", [])
print(f"tenant B companies: {len(items)}")
PY

echo "Attempting to access tenant A company with tenant B header (should be 404/403)..."
STATUS=$(curl -sS -o /tmp/company_b_attempt.json -w "%{http_code}" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "X-Tenant: ${TENANT_B}" \
  "${API_BASE}/api/v1/companies/${COMPANY_A_ID}")

echo "Status: ${STATUS}"
if [[ "$STATUS" != "403" && "$STATUS" != "404" ]]; then
  echo "Unexpected status when accessing cross-tenant data: ${STATUS}" >&2
  exit 1
fi

echo "OK: tenant isolation checks passed for basic company reads."

echo "Next manual checks:"
cat <<'NOTE'
- Verify outbox entries contain tenant_id for each tenant.
- Ensure no events from tenant A appear when filtering tenant B outbox.
- Verify metrics labeling per tenant (outbox_*).
NOTE
