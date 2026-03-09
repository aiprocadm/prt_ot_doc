# FINAL ACCEPTANCE REPORT (by TZ)

Дата: 2026-03-09

## 1. Acceptance criteria and status

| Criterion | Implementation coverage | Test coverage | Status | Notes/Risks |
|---|---|---|---|---|
| Повторный POST с тем же Idempotency-Key возвращает тот же id | idempotency service + guarded routes | `tests/test_idempotency.py`, `tests/integration/test_idempotency_generate.py`, `tests/e2e/final_regression/*` | PASS | Есть replay/conflict проверки |
| Любой business route без X-Tenant => 400 | tenant middleware/deps | `tests/test_tenant_header_required.py`, `tests/e2e/final_regression/*` | PASS | Сохранять как P0 gate |
| Template choice strictly by (code, version) | templates service/api | `tests/test_template_delete.py`, `tests/test_templates_pipeline_api.py` | PASS | Контракт 409 на missing/conflict |
| Delete in-use template version => 409 | templates guard | `tests/test_template_delete.py` | PASS | |
| EDO outgoing + webhook <= 60s | edo/sign/outbox/webhooks | functional tests exist | PARTIAL | SLA <=60s нужен stage perf test |
| Risk maps built from dictionaries | risk services | `tests/test_risk_engine.py` + related | PARTIAL | словари есть, требуется полная UAT матрица |
| PPE journals correct | ppe services/api | `tests/api/test_ppe_api.py`, `test_ppe_events.py` | PASS | |
| PDF with embedded font | pdf module | `tests/test_services_pdf_unit.py` | PARTIAL | нужен explicit font-embed assertion |
| Replace dry-run/apply/rollback | replace module + jobs | `tests/test_replace_api.py`, pipeline tests | PARTIAL | corner-cases расширить |
| Client cabinet statuses + ZIP/PDF links + history | client_portal module/pages | `tests/test_client_portal_api.py` | PARTIAL | требуется расширенный e2e UX/security |
| KPI dashboards + XLSX/PDF exports | reports/export modules | `tests/api/test_reports_api.py` | PARTIAL | нужны end-user export journey tests |
| Import mismatch log | replace/report and import utilities | частичные unit tests | PARTIAL | унифицировать mismatch reporting |
| Tests green | pytest suites | `make final-acceptance` | PASS* | по подмножеству critical/regression |
| Coverage target met | CI metric | N/A in current local run | PARTIAL | зафиксировать целевое значение в CI |
| Backup/restore passed | ops/runbook | docs only in this run | PARTIAL | нужен scripted restore rehearsal |
| SLA/SLO measured | perf report baseline | `docs/FINAL_PERF_REPORT.md` | PARTIAL | нет stage нагрузочного профиля |

## 2. Overall conclusion
- RC готов для UAT/пилота с известными ограничениями (perf SLA instrumentation, full portal e2e leakage matrix, font-embed formal check).
- P0/Pcritical guardrails по tenant/idempotency/template-delete/health/openapi присутствуют и собраны в единый final-acceptance gate.
