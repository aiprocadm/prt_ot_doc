# PROJECT_CONTEXT_PACK

## 1) Фактическая архитектура
- Backend: FastAPI + SQLAlchemy + Alembic + Celery worker; единый API роутер собирается в `app/api/v1/router.py`, бизнес-маршруты подключаются через `tenant_router` и требуют tenant dependency/middleware.  
- Tenant enforcement: middleware валидирует `X-Tenant`, сопоставляет с tenant в БД и блокирует mismatch с JWT scope.  
- Data model: tenant-aware таблицы + tenancy helpers/scoping; миграции в `backend/app/migrations/versions` покрывают tenancy, authz, pipeline, analytics/export и safety-модули.  
- Frontend: React/Vite с route-based страницами по доменам (templates, files, edo, approvals, incidents, ppe, analytics, exports, client portal).

## 2) Стек
- FastAPI, Pydantic v2, SQLAlchemy/Alembic, PostgreSQL (tenant schema model), Celery/Redis, S3/MinIO adapters, React + TypeScript + Vite.

## 3) Реально существующие backend-модули
- Документы/шаблоны/replace/pdf/pipelines: `modules/templates`, `modules/replace`, `modules/pdf`, `modules/pipelines`, `api/routes/documents.py`.  
- EDO/approval/sign/webhooks/outbox: `modules/edo`, `modules/approval`, `modules/approvals`, `modules/sign`, `api/routes/webhooks.py`, `api/routes/outbox_admin.py`.  
- Safety verticals: `modules/risk`, `modules/ppe`, `modules/incidents`, `modules/inspections`, `modules/capa`, `modules/training`, `modules/briefings`.  
- Cross-cutting: `modules/rbac_abac`, `modules/audit`, `core/idempotency.py`, `middleware/tenant.py`, `modules/files`.

## 4) Реально существующие frontend-разделы
- Админ/доступ/аудит/настройки/dashboard, документы/шаблоны/files/packs/tasks, risk/ppe/incidents/inspections, analytics/exports, client portal (`frontend/src/pages/**`).

## 5) Основные доменные сущности
- Tenant, TenantSettings, TenantQuota; Document/Template/TemplateVersion; Approval/Sign/EDO Message; File/FileVersion; Risk/PPE/Incident/Inspection; Job/PipelineRun; AuditLog/Outbox/Webhook delivery.

## 6) Сквозной document pipeline (по коду)
- Template version upload/lint/preview/render -> replace dry-run/apply -> headers/layout -> pdf conversion -> approval/sign/edo -> archive/export/search projections.

## 7) Что уже отражено в коде по ТЗ
- Обязательный tenant header на бизнес API, JWT tenant scope check, RBAC/ABAC infra, audit + immutable tests, idempotency сервис и тесты, pipeline orchestrator/tests, webhooks/outbox retry/dedupe tests.

## 8) Что частично/отсутствует
- Часть enterprise-уровня (полный DR/backup automation, полнофункциональный offline/PWA sync, production-grade AV/DLP policy) реализована частично и требует hardening.

## 9) Точки входа для запуска/проверки
- `make cs:dev`, `make cs:test`, `make codex-audit`, `make final-acceptance`, `scripts/pilot_readiness.py`.

## 10) Опасные неизвестные/техдолг
- Много SQLAlchemy warnings по overlaps в risk models.
- Есть исторические/legacy key-prefix в файловом модуле; сохранена обратная совместимость, но требуется миграция ключей на единый namespace.
- Есть большой набор docs/отчетов; риск расхождения «документ vs код» без регулярного прогонов `make codex-audit`.
