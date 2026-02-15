# TZ_COMPLIANCE

Статусы: **OK / Partial / Missing**.
Приоритеты: **P0** (блокер), **P1** (важно), **P2** (улучшение).

## A–I matrix

| Block | Requirement | Evidence | Status | Priority / Gap |
|---|---|---|---|---|
| A. Multi-tenant | `X-Tenant` обязателен на бизнес `/api/v1/*`; tenant-scoped операции | `backend/app/middleware/tenant.py`, `backend/app/core/tenant.py`, `frontend/src/api/client.ts`, `tests/test_tenant_header_required.py` | OK | — |
| B. Roles & access | RBAC + ABAC с company/site/document/status/risk атрибутами | `backend/app/core/security.py`, `tests/test_rbac_abac.py`, `tests/unit/test_abac_policies.py` | Partial | **P1:** расширить ABAC-покрытие на все mutation endpoints |
| C. Audit append-only | immutable audit log c metadata | `tests/test_audit_log_immutability.py`, `backend/app/api/v1/audit.py` | OK | — |
| D. Core entities | контрагенты/договоры/заказы/счета/оргструктура/сотрудники/документы | `backend/app/api/v1/*`, `backend/app/models/*`, `tests/integration/test_finance_entities.py` | Partial | **P1:** углубить контуры обязательств/регистров в UI |
| E. Documents/processes | template→instance→version, delete referenced=409 | `tests/test_template_delete.py`, `tests/test_documents_generate.py`, `backend/app/api/v1/documents.py` | OK | **P2:** QR/водяные знаки и richer low-code workflow deferred |
| F. Idempotency/outbox/webhooks | Idempotency-Key, outbox retries/dlq/metrics, tenant webhook override | `backend/app/core/idempotency.py`, `backend/app/services/outbox.py`, `backend/app/services/webhooks.py`, `tests/test_idempotency.py` | OK | — |
| G. Domain modules | risks/PPE/training/incidents/inspections MVP working contour | `tests/test_risk_assessment_kpi5.py`, `tests/api/test_ppe_api.py`, `tests/api/test_training_api.py`, `tests/api/test_incidents_api.py` | Partial | **P1:** доразвить проверки/предписания и workflow depth |
| H. Obligations/deadlines | реестр задач, автогенерация по событиям, overdue/reminders | `backend/app/api/v1/obligations.py`, `backend/app/api/v1/tasks.py`, `tests/integration/test_obligation_tasks.py`, `tests/unit/test_task_reminders.py` | Partial | **P1:** расширить напоминания/отчёты в UI |
| I. DevX/quality | Codespaces open→run, dockerless, test discovery, docs | `.devcontainer/devcontainer.json`, `.github/workflows/ci.yml`, `docs/runbook-codespaces.md`, `docs/testing.md` | OK | — |

## KPI coverage
- KPI-1 Idempotency `/documents:generate`: **OK** (`tests/test_idempotency.py`).
- KPI-2 Missing tenant header → 400: **OK** (`tests/test_tenant_header_required.py`).
- KPI-3 template_code+version strict + delete referenced→409: **OK** (`tests/test_template_delete.py`).
- KPI-4 Event → outbox → webhook (dev mock): **OK** (`tests/test_outbox_dispatch.py`, `tests/test_webhooks_dispatch.py`).
- KPI-5 Deterministic risk cards + action plan: **OK** (`tests/test_risk_assessment_kpi5.py`).

## Security & Tenant Isolation Risks
- **P1:** новые или редкие mutation endpoints должны продолжать применять ABAC-политики, не только role-check.
- **P1:** при расширении модулей важно сохранять tenant-scoped repository filters по умолчанию.

## DevX & Codespaces Risks
- **Resolved P0:** devcontainer переведён на dockerless-first (без `dockerComposeFile`).
- **Resolved P1:** test discovery включает `integration_tests` в pytest/vscode/devcontainer settings.
- **Open P1:** cold start дорогой из-за полного reinstall зависимостей в lite-скриптах.

## Docs Consistency Risks
- **Resolved P0:** единый CI workflow в `.github/workflows/ci.yml`.
- **Resolved P1:** добавлен единый testing guide (`docs/testing.md`).
- **Resolved P1:** README сокращён до quick-start + ссылки на source-of-truth документы.

## GAP list

### P0
- Нет открытых P0 после текущего прохода.

### P1
1. Расширить ABAC enforcement на все mutation endpoints.
2. Расширить UI/аналитику obligations (overdue/reminders/reports).
3. Уменьшить cold-start время `make dev:lite`/`make test:lite`.

### P2
1. QR/водяные знаки и расширенные EDI-протоколы.
2. Углубление low-code маршрутов и WS/real-time контуров.
