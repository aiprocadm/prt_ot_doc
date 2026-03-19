#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

OUT_DIR="artifacts/final_acceptance"
mkdir -p "$OUT_DIR"
JSON_OUT="$OUT_DIR/summary.json"
MD_OUT="$OUT_DIR/summary.md"
: > "$MD_OUT"

echo "# Final Acceptance Summary" >> "$MD_OUT"
echo "" >> "$MD_OUT"

if [ ! -d ".venv" ]; then
  python -m venv .venv
fi
source .venv/bin/activate

python -m pip install -q -r requirements.txt -r requirements-dev.txt

STATUS=0
RESULTS_JSON='[]'

run_check() {
  local name="$1"
  local cmd="$2"
  local required="${3:-true}"
  local safe_name="${name//[^a-zA-Z0-9._-]/_}"
  local log="$OUT_DIR/${safe_name}.log"

  echo "Running: $name"
  set +e
  bash -lc "$cmd" >"$log" 2>&1
  local code=$?
  set -e

  local result="pass"
  if [ $code -ne 0 ]; then
    if [ "$required" = "true" ]; then
      result="fail"
      STATUS=1
    else
      result="warn"
    fi
  fi

  RESULTS_JSON=$(python - <<PY
import json
items = json.loads('''$RESULTS_JSON''')
items.append({"name": "$name", "command": "$cmd", "status": "$result", "exit_code": $code, "log": "$log"})
print(json.dumps(items, ensure_ascii=False))
PY
)

  printf -- "- **%s**: %s (%s)\n" "$name" "$result" "$cmd" >> "$MD_OUT"
}

run_check "critical backend tests" "./scripts/pytest.sh tests/test_tenant_header_required.py tests/test_idempotency.py -k 'not pack_run' tests/test_template_delete.py tests/test_outbox_dispatch.py"
run_check "critical frontend checks" "cd frontend && npm ci && npm run test" false
run_check "e2e final regression subset" "./scripts/pytest.sh tests/e2e/final_regression"
run_check "openapi drift" "./scripts/pytest.sh tests/contract/test_openapi_contract.py && PYTHONPATH=backend python scripts/contract/validate.py"
run_check "migrations heads" "PYTHONPATH=backend python -m alembic -c backend/app/migrations/alembic.ini heads" false
run_check "health and readiness" "./scripts/pytest.sh tests/test_health_ready.py"
run_check "sample render/pdf/export flow" "./scripts/pytest.sh tests/test_package_pipeline.py tests/test_services_pdf_unit.py"
run_check "schema consistency" "PYTHONPATH=backend python scripts/verify_schema_consistency.py"
run_check "release docs presence" "./scripts/pytest.sh tests/e2e/test_release_candidate_docs.py"
run_check "perf tooling foundation" "python scripts/perf/api_load.py --help" false

python - <<PY
import json
from datetime import datetime, timezone

items = json.loads('''$RESULTS_JSON''')
summary = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "overall_status": "pass" if all(i["status"] != "fail" for i in items) else "fail",
    "checks": items,
}
with open("$JSON_OUT", "w", encoding="utf-8") as fh:
    json.dump(summary, fh, ensure_ascii=False, indent=2)
PY

echo "" >> "$MD_OUT"
echo "Artifacts:" >> "$MD_OUT"
echo "- JSON: $JSON_OUT" >> "$MD_OUT"
echo "- Logs: $OUT_DIR/*.log" >> "$MD_OUT"

exit "$STATUS"
