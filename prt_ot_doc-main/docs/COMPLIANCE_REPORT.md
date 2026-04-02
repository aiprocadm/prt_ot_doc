# SPEC ↔ CODE Compliance Report (TZ Audit)

## Phase 0 — Architecture map

### Backend
- **Entrypoints**: FastAPI app factory and entrypoint in `backend/app/api/app.py` and `backend/app/main.py`; Celery tasks in `backend/app/tasks.py`; worker bootstrap in `backend/app/worker.py`. 
- **Routers**: v1 API router wiring in `backend/app/api/v1/router.py` with feature routers mounted beneath `/api/v1`.
- **Auth & access control**: JWT issuance/verification + RBAC/ABAC in `backend/app/core/security.py` with role and attribute checks; tenant is validated in middleware (`backend/app/middleware/tenant.py`) and request dependencies (`backend/app/api/dependencies.py`).
- **Tenant propagation**: header validation + token scope checks in middleware; DB sessions use tenant-aware search paths in `backend/app/db/session.py`.
- **DB + migrations**: SQLAlchemy models in `backend/app/models/models.py`; Alembic migrations in `backend/app/migrations/`.
- **Queues**: Celery task definitions and dispatchers in `backend/app/tasks.py`.
- **Storage**: S3/MinIO integration in `backend/app/domains/files/s3.py`, file storage service in `backend/app/services/file_storage.py`.
- **Metrics/observability**: Prometheus metrics in `backend/app/core/metrics.py`, tracing in `backend/app/core/tracing.py`, and observability middleware in `backend/app/middleware/observability.py`.

### Frontend
- **Stack**: React + Vite SPA under `frontend/` with API client in `frontend/src/api/client.ts` and tenant store in `frontend/src/stores/tenant.ts`.
- **Tenant context**: `frontend/src/api/client.ts` injects `X-Tenant` and blocks protected requests without a selected tenant.

### Infra/dev
- **Compose**: `docker-compose.yml` defines local services for API, worker, Postgres, Redis, MinIO, etc.
- **Devcontainer**: `.devcontainer/` contains Codespaces configuration.
- **Tests**: `pytest`-based backend tests under `tests/` and frontend tests under `frontend/src/__tests__/`.

## Phase 1 — Compliance matrix (SPEC ↔ CODE)

| SPEC requirement | Current implementation (files/modules) | Status | Severity | Fix plan |
| --- | --- | --- | --- | --- |
| Product positioning (ERP‑core + отраслевые модули RiskProf/OTOR/KOT) | Документация и доменные модули в `docs/`, `backend/app/domains`, `frontend/src`. | Partial | P2 | Уточнять маркетинговое описание по мере развития. |
| Core: пользователи/роли/доступы | JWT + RBAC/ABAC в `backend/app/core/security.py`, роли в моделях. | OK | P0 | None. |
| Core: организации и оргструктура | Модели и роуты компаний/филиалов/подразделений/площадок. | OK | P1 | None. |
| Core: мастер‑данные/справочники | Реестр NPA/risks/PPE dictionaries в доменных сервисах. | OK | P1 | None. |
| Core: сотрудники (обучение/медосмотры/СИЗ/риски) | Доменные модули training/medical/ppe/risk. | OK | P1 | None. |
| Core: документы (template→instance→version→signatures→protocols) | Шаблоны/версии/пайплайны в `documents` и `pipeline`. | Partial | P1 | Документировать статус подписаний/протоколов. |
| Core: сроки/обязательства/напоминания | `services/obligations.py` + tasks reminders. | Partial | P1 | Расширить охват на проверки/аттестации по запросу. |
| Core: события/уведомления | Outbox + webhook сервисы в `services/outbox.py`, `services/webhooks.py`. | OK | P0 | None. |
| Core: аудит (append‑only) | `AuditLog` + блокировка UPDATE/DELETE и `AuditService`. | OK | P0 | None. |
| API + интеграции (outbox/webhooks) | Outbox dispatcher, retries, DLQ, metrics. | OK | P0 | None. |
| Multi‑tenancy: tenant header + DB isolation | Tenant middleware + tenant‑scoped sessions. | OK | P0 | None. |
| /v1 бизнес‑роут без X‑Tenant → 400 | Принудительный guard в middleware + tests. | OK | P0 | None. |
| RBAC + ABAC атрибуты (company/site/document/status/risk) | `AccessContext` и политики в security. | OK | P1 | None. |
| Идемпотентность критичных операций | `IdempotencyService` + headers in documents/packs/risk. | OK | P0 | None. |
| Документы: строгий выбор (template_code, version) + delete 409 | Валидация в documents routes + guards on version delete. | OK | P0 | None. |
| DOCX→PDF + штампы/QR/водяные знаки | DOCX→PDF pipeline; QR/watermark как optional stage. | Partial | P2 | Добавить этапы при необходимости продукта. |
| Риски: методики и детерминированные карты/планы | Risk engine + dictionaries in `risk` domain. | OK | P0 | None. |
| СИЗ: нормы/журналы выдачи/возврата | PPE routes + journal endpoints. | OK | P1 | None. |
| Обучение/инструктажи | Training programs/sessions/results + журналы. | OK | P1 | None. |
| Инциденты/проверки/предписания | Incidents OK; inspections/prescriptions частично. | Partial | P2 | Роадмап, если требуется MVP. |
| Outbox → webhook delivery ≤60s | Retry policy + worker scheduling. | OK | P0 | None. |
| Frontend: X‑Tenant injection + блокировка без контекста | API client + tenant store in `frontend/src`. | OK | P0 | None. |
| DevX: запуск в Codespaces + pytest discovery | `.devcontainer`, `.vscode/settings.json`, Makefile targets. | OK | P0 | None. |

## Phase 1 — Prioritized gap list

- **P0**: _No P0 gaps detected_ based on current implementation.
- **P1**:
  - Expand obligations engine beyond training/medical to inspections/attestations (if required).
- **P2**:
  - Add explicit QR/watermark pipeline stage if mandated by UX/spec.
  - Add inspection/prescription scaffolding for incident workflows.

## Security & Tenant Isolation Risks
- Tenant isolation relies on `X-Tenant` + token scope checks; ensure all new routes remain behind middleware and tenant-aware DB sessions.
- Audit log immutability is enforced via SQLAlchemy events; avoid direct SQL UPDATE/DELETE bypasses.

## Runability Risks
- None observed for current devcontainer + compose flow; ensure `.env` is created from `.env.example` before startup.

## Test Discovery Risks
- None observed: `pytest` configuration is present and `.vscode/settings.json` enables VS Code Testing discovery.

## Phase 2 — P0 fixes implemented

No additional P0 fixes required; implementation already satisfies KPIs 1–5.

## Phase 3 — P1 fixes (optional)

Not required for this pass.

## Phase 4 — Tests & runbook

### Runbook (Codespaces/local)
- Backend (API):
  - `cp .env.example .env`
  - `make run`
- Backend tests:
  - `make test`
  - `pytest --collect-only`
- Frontend:
  - `cd frontend && npm install && npm run dev`

### Manual QA checklist (KPI-1..KPI-5)
- **KPI-1**: Repeat `POST /api/v1/documents/generate` with same `Idempotency-Key` and identical payload; confirm `document_version_id` is stable.
- **KPI-2**: Call any `/api/v1/*` business route without `X-Tenant` and confirm `400`.
- **KPI-3**: Request a template by `(template_code, version)` and attempt to delete a version referenced by a document; expect `409`.
- **KPI-4**: Trigger a document generation or PPE issuance and confirm outbox entry is dispatched and webhook delivered within 60s.
- **KPI-5**: Run a risk assessment and confirm deterministic risk cards/action plan from dictionaries.
- **P1**: Создать инспекцию и аттестацию, убедиться в появлении задач в `/api/v1/tasks` и в отправке `TaskDueSoon/TaskOverdue` через outbox.
