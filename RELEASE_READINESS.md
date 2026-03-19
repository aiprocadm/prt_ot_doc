# RELEASE_READINESS

## Overall status
**Release candidate candidate status: READY FOR PILOT / DEMO, CONDITIONALLY READY FOR CONTROLLED RC DEPLOYMENT.**

## Readiness checklist
- [x] Critical tenant isolation checks are automated.
- [x] Core document/package/idempotency paths are covered.
- [x] Approval/sign/EDO API flow is regression-tested.
- [x] Workflow delegation/escalation path is regression-tested.
- [x] Export/report async status tracking is regression-tested.
- [x] Structured API error envelope is normalized and regression-tested.
- [x] Smoke/final acceptance scripts exist for repeatable verification.
- [x] Lightweight performance probe exists for pilot/stage hot-path review.
- [x] Known limitations are documented.
- [ ] Environment-specific backup/restore rehearsal completed.
- [ ] External provider certification completed for non-mock integrations.

## Verification bundle
```bash
./scripts/pytest.sh tests/test_errors.py tests/contract/test_openapi_contract.py
./scripts/pytest.sh tests/e2e/final_regression/test_final_regression_api.py
./scripts/pytest.sh tests/integration/test_tenant_isolation.py tests/integration/test_job_status_flow.py
./scripts/pytest.sh tests/api/test_edo_signature_approval_mvp.py tests/api/test_exports_foundation_api.py
./scripts/pytest.sh tests/test_workflow_api.py tests/test_billing_service.py
python scripts/perf/api_load.py --base-url http://localhost:8000 --path /health --requests 25 --concurrency 5
npm --prefix frontend run test
```

## Demo / pilot prerequisites
1. Provision PostgreSQL/Redis/object storage with tenant bootstrap data.
2. Configure at least one demo tenant and admin user.
3. Decide whether EDO/signature/integration flows run in mock or certified provider mode.
4. Capture acceptance and perf command outputs as deployment evidence.
5. Confirm migration head, OpenAPI contract validation, and release notes review before cut.
