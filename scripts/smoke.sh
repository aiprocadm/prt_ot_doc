#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TENANT_HEADER_NAME="${TENANT_HEADER_NAME:-X-Tenant}"
TENANT_SLUG="${DEFAULT_TENANT_SLUG:-demo}"

for _ in $(seq 1 60); do
  if curl -fsS "${BASE_URL}/readyz" >/dev/null; then
    break
  fi
  sleep 2
done
curl -fsS "${BASE_URL}/readyz" >/dev/null

PYTHONPATH=backend python -m alembic -c backend/app/migrations/alembic.ini upgrade heads
PYTHONPATH=backend python scripts/create_tenant.py "${TENANT_SLUG}" "Demo Tenant" "demo@example.local" || true
PYTHONPATH=backend python scripts/migrate_tenant.py "${TENANT_SLUG}" || true

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

echo "smoke passed"
