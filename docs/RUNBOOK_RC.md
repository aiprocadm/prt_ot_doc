# RC Runbook

## 1) Bootstrap
```bash
make install-pip
cd frontend && npm ci
```

## 2) Backend checks
### Targeted critical checks
```bash
source .venv/bin/activate
pytest -q tests/test_cli_main.py
pytest -q tests/integration/test_idempotency_generate.py tests/integration/test_job_status_flow.py tests/test_api_guardrails.py
```

### Full suite (optional, long)
```bash
source .venv/bin/activate
pytest -q
```

## 3) Frontend checks
```bash
cd frontend
npm run build
npm test
```

## 4) Smoke testing (minimum)
- Backend health + protected route behavior: use API guardrails/tenant tests and local API run.
- Job pipeline/idempotency: execute integration tests listed above.
- Frontend critical routes: validated by production build + test suite.

## 5) Local RC validation flow
1. Install deps (python + frontend).
2. Run targeted backend critical tests.
3. Run frontend build and tests.
4. If environment has docker/postgres, run migration and full smoke scripts.
5. Review docs:
   - `docs/RELEASE_CANDIDATE_AUDIT.md`
   - `docs/ACCEPTANCE_CHECKLIST.md`
   - `docs/CI_STABILIZATION_REPORT.md`
   - `docs/KNOWN_LIMITATIONS_RC.md`
