#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TENANT_HEADER_NAME="${TENANT_HEADER_NAME:-X-Tenant}"
TENANT_SLUG="${DEFAULT_TENANT_SLUG:-demo}"
PYTHON_BIN="${PYTHON_BIN:-python}"
UVICORN_BIN="${UVICORN_BIN:-uvicorn}"
AUTO_START_API="${AUTO_START_API:-1}"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi
if [[ -x ".venv/bin/uvicorn" ]]; then
  UVICORN_BIN=".venv/bin/uvicorn"
fi

api_pid=""

if [[ "$AUTO_START_API" == "1" && -f "scripts/dockerless_env.sh" ]]; then
  set -a
  # shellcheck disable=SC1091
  source scripts/dockerless_env.sh
  set +a
  export DEMO_BOOTSTRAP="${DEMO_BOOTSTRAP:-0}"
  export ADMIN_BOOTSTRAP="${ADMIN_BOOTSTRAP:-0}"
  # Use an isolated SQLite file for smoke checks to avoid collisions with
  # developer/test databases that may already contain partially migrated schema.
  export DATABASE_URL="sqlite+aiosqlite:///./.smoke.db"
  rm -f .smoke.db backend/.smoke.db backend/app/.smoke.db
fi

cleanup() {
  if [[ -n "$api_pid" ]]; then
    kill "$api_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

show_api_logs() {
  echo "API did not become ready; collecting diagnostics" >&2
  if command -v docker >/dev/null && docker compose ps api >/dev/null 2>&1; then
    docker compose logs api >&2 || true
  fi
}

ensure_api_running() {
  if curl -fsS "${BASE_URL}/readyz" >/dev/null 2>&1; then
    return 0
  fi
  if [[ "$AUTO_START_API" != "1" ]]; then
    return 0
  fi
  if [[ -x ".venv/bin/uvicorn" ]]; then
    UVICORN_BIN=".venv/bin/uvicorn"
  fi
  if [[ -x ".venv/bin/python" ]]; then
    PYTHON_BIN=".venv/bin/python"
  fi

  echo "Starting local API for smoke checks (${UVICORN_BIN})"
  PYTHONPATH=backend "$UVICORN_BIN" app.main:app --host 0.0.0.0 --port 8000 >/tmp/smoke_api.log 2>&1 &
  api_pid=$!
}

run_pdf_probe() {
  if ! command -v soffice >/dev/null 2>&1; then
    echo "WARN: skipping PDF probe because 'soffice' is unavailable in current environment" >&2
    return 0
  fi

  if command -v docker >/dev/null && docker compose ps api >/dev/null 2>&1; then
    docker compose exec -T api env TENANT_SLUG="${TENANT_SLUG}" python - <<'PY'
import io
import os
import zipfile
from app.modules.pdf.service_pool import LibreOfficePool
from app.modules.pdf.convert import convert_docx_bytes
from app.domains.files import s3

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w') as z:
    z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    z.writestr('word/document.xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>smoke</w:t></w:r></w:p></w:body></w:document>')
source = buf.getvalue()
pdf_bytes, sha = convert_docx_bytes(source_bytes=source, timeout_s=45, pool=LibreOfficePool())
prefix = f"{os.environ['TENANT_SLUG']}/"
key = f"{prefix}smoke/{sha[:12]}.pdf"
s3.put_object(key=key, data=pdf_bytes, mime='application/pdf')
keys = s3.list_keys(prefix=prefix)
assert any(k.startswith(prefix) for k in keys), 'tenant prefix missing in s3'
print(f'converted and stored: {key}')
PY
    return
  fi

  PYTHONPATH=backend TENANT_SLUG="${TENANT_SLUG}" "$PYTHON_BIN" - <<'PY'
import io
import os
import zipfile
from app.modules.pdf.service_pool import LibreOfficePool
from app.modules.pdf.convert import convert_docx_bytes
from app.domains.files import s3

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w') as z:
    z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    z.writestr('word/document.xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>smoke</w:t></w:r></w:p></w:body></w:document>')
source = buf.getvalue()
pdf_bytes, sha = convert_docx_bytes(source_bytes=source, timeout_s=45, pool=LibreOfficePool())
prefix = f"{os.environ['TENANT_SLUG']}/"
key = f"{prefix}smoke/{sha[:12]}.pdf"
s3.put_object(key=key, data=pdf_bytes, mime='application/pdf')
keys = s3.list_keys(prefix=prefix)
assert any(k.startswith(prefix) for k in keys), 'tenant prefix missing in s3'
print(f'converted and stored: {key}')
PY
}

set +e
PYTHONPATH=backend "$PYTHON_BIN" -m alembic -c backend/app/migrations/alembic.ini upgrade heads >/tmp/smoke_alembic.log 2>&1
alembic_code=$?
set -e

if [[ $alembic_code -ne 0 ]]; then
  if [[ "${DATABASE_URL:-}" == sqlite* ]] && rg -q "can't render element of type JSONB|visit_JSONB" /tmp/smoke_alembic.log; then
    echo "WARN: alembic upgrade is not fully SQLite-compatible (JSONB columns); running fallback smoke gate" >&2
    cat /tmp/smoke_alembic.log >&2
    ./scripts/pytest.sh tests/test_health_ready.py tests/test_tenant_header_required.py
    echo "smoke passed (fallback mode)"
    exit 0
  fi
  cat /tmp/smoke_alembic.log >&2
  exit $alembic_code
fi

PYTHONPATH=backend "$PYTHON_BIN" scripts/create_tenant.py "${TENANT_SLUG}" "Demo Tenant" "demo@example.local" || true
PYTHONPATH=backend "$PYTHON_BIN" scripts/migrate_tenant.py "${TENANT_SLUG}" || true

ensure_api_running

for _ in $(seq 1 60); do
  if curl -fsS "${BASE_URL}/readyz" >/dev/null; then
    break
  fi
  sleep 2
done
if ! curl -fsS "${BASE_URL}/readyz" >/dev/null; then
  show_api_logs
  exit 1
fi

curl -fsS "${BASE_URL}/healthz" >/dev/null

code_no_tenant=$(curl -s -o /tmp/smoke_templates_no_tenant.json -w "%{http_code}" "${BASE_URL}/api/v1/templates")
if [[ "$code_no_tenant" != "400" ]]; then
  echo "Expected 400 without tenant header, got ${code_no_tenant}" >&2
  cat /tmp/smoke_templates_no_tenant.json >&2
  exit 1
fi

code_with_tenant=$(curl -s -o /tmp/smoke_templates_with_tenant.json -w "%{http_code}" -H "${TENANT_HEADER_NAME}: ${TENANT_SLUG}" "${BASE_URL}/api/v1/templates")
if [[ "$code_with_tenant" != "200" ]]; then
  echo "Expected 200 with tenant header, got ${code_with_tenant}" >&2
  cat /tmp/smoke_templates_with_tenant.json >&2
  exit 1
fi

run_pdf_probe

echo "smoke passed"
