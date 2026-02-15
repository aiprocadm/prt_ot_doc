# TZ_COMPLIANCE

Статусы: **OK / Partial / Missing**. Приоритеты: **P0 / P1 / P2**.

## Matrix (SPEC ↔ CODE)

| Раздел ТЗ | Требование | Где в коде | Статус | Severity | План/статус фикса |
|---|---|---|---|---|---|
| Multitenant | `/v1` бизнес-роуты без `X-Tenant` → 400 | `backend/app/middleware/tenant.py`, `backend/app/core/tenant.py`, `tests/test_tenant_header_required.py`, `frontend/src/api/client.ts` | OK | P0 | Закрыто |
| Roles | RBAC + ABAC | `backend/app/core/security.py`, `tests/test_rbac_abac.py`, `tests/unit/test_abac_policies.py` | Partial | P1 | Расширять ABAC coverage на редкие mutation endpoints |
| Audit | Append-only, запрет update/delete | `backend/app/models/models.py`, `tests/test_audit_log_immutability.py` | OK | P0 | Закрыто |
| Documents | template→instance→version, strict `(template_code, version)` | `backend/app/api/routes/documents.py`, `tests/test_template_delete.py` | OK | P0 | Закрыто |
| Idempotency | повторный generate с тем же key возвращает тот же результат | `backend/app/services/idempotency.py`, `tests/test_idempotency.py` | OK | P0 | Закрыто |
| Outbox/webhooks | retries/backoff/dead-letter/metrics + routing global/per-tenant | `backend/app/services/outbox.py`, `backend/app/services/webhooks.py`, `tests/test_outbox_dispatch.py`, `tests/test_webhook_routing.py` | OK | P0 | Закрыто |
| Domain events | `DocumentGenerated/Signed/Exported/RiskAssessed/PPEIssued/TrainingCompleted` | `backend/app/services/events.py`, `tests/api/test_document_events.py`, `tests/api/test_ppe_events.py`, `tests/api/test_training_api.py`, `tests/test_risk_engine.py` | OK | P0 | Закрыто |
| Risks | детерминированная оценка + action plan | `backend/app/services/risk.py`, `tests/test_risk_assessment_kpi5.py` | OK | P0 | Закрыто |
| Obligations | единый реестр задач + reminders/overdue | `backend/app/services/obligations.py`, `backend/app/services/tasks.py`, `tests/unit/test_task_reminders.py` | Partial | P1 | Усилить UI отчёты/фильтры overdue |
| DevX | open→run в Codespaces, test discovery | `Makefile`, `.devcontainer/devcontainer.json`, `docs/runbook-codespaces.md`, `docs/testing.md` | OK | P0 | Закрыто: pip-only + cs:* команды |

## KPI status
- KPI-1: **OK** (`tests/test_idempotency.py`).
- KPI-2: **OK** (`tests/test_tenant_header_required.py`).
- KPI-3: **OK** (`tests/test_template_delete.py`).
- KPI-4: **OK** (`tests/test_outbox_dispatch.py`, `tests/test_webhook_routing.py`).
- KPI-5: **OK** (`tests/test_risk_assessment_kpi5.py`).

## Security & Tenant Isolation Risks
- **P1:** ABAC нужно расширять при добавлении новых write-endpoints.

## DevX/Codespaces Risks
- **Closed P0:** устранён конфликт Poetry vs pip для основного сценария (Makefile pip-first).
- **Closed P0:** добавлены каноничные команды `cs:dev`, `cs:test`, `cs:reset`.

## Test Discovery Risks
- **Closed P0:** discovery не зависит от внешнего Redis (default `RATE_LIMIT_STORAGE_URI=memory://`).

## Repo Hygiene Risks
- **Closed P1:** devcontainer больше не устанавливает poetry как обязательный инструмент.
- **P2:** сохранить `poetry.lock` как вторичный артефакт или удалить в следующем cleanup PR после решения команды.
