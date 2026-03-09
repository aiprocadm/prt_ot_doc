# PROJECT_CONTEXT_PACK

## 1) Фактическая архитектура
- Монорепозиторий: `backend` (FastAPI), `frontend` (React + Vite), `tests`, `docs`, `scripts`, `docker-compose`.
- Вход API: `backend/app/api/v1/router.py`; почти все business-маршруты подключены через `tenant_router` c `require_tenant_slug`. 
- Tenant enforcement дополнительно обеспечивается middleware `TenantMiddleware` (валидация заголовка, tenant lookup, tenant context в request.state).
- Асинхронные задачи: Celery tasks через `app/services/tasks.py` + celery модуль.
- БД: SQLAlchemy + Alembic migrations в `backend/app/migrations/versions`.

## 2) Стек
- Backend: FastAPI, Pydantic v2, SQLAlchemy async, Alembic, Celery, Redis/PostgreSQL (по инфраструктурным файлам).
- Frontend: React 18, TypeScript, Vite, Zustand, React Router, Vitest.
- Инфра: Docker Compose, Make targets для dev/test/migrate.

## 3) Реально существующие backend-модули
- API routes: auth, tenants, tenancy, templates/documents/packs/pipelines, files, audit, billing, outbox/webhooks, client portal, risk, incidents, inspections, prescriptions, training, ppe, reports, analytics/export/search и др.
- Доменные/модульные папки: `backend/app/domains/*` и `backend/app/modules/*` (audit, files, pipelines, rbac_abac, client_portal, search, export_center, pwa_sync и др.).

## 4) Реально существующие frontend-разделы
- Роутинг: `frontend/src/router/AppRouter.tsx`.
- Разделы: dashboard, companies/persons, templates, documents/wizard, files, tasks/jobs, risk, ppe, training, medical, incidents, inspections, audit, reports/exports/analytics, client portal, approvals/edo/signatures, admin/outbox/billing/settings.

## 5) Основные доменные сущности (по моделям/роутам)
- Tenant, TenantQuota, TenantSettings, Users/Roles.
- Templates + TemplateVersion.
- PipelineRun/pack runs/jobs/outbox events.
- Companies, Sites, Persons, Training, Medical, PPE.
- Incidents, Inspections, Prescriptions, Risk entities.
- Files/documents/audit events/webhooks.

## 6) Pipeline документа
- В коде и документации отражены этапы шаблона, replace/layout/pipeline run, генерация PDF/документов, задания в очереди, job tracking, audit и integrations hooks.
- Есть отдельные API и модули для replace (`modules/replace`), pipelines (`modules/pipelines`), packs (`api/routes/packs.py`).

## 7) Что по ТЗ уже явно отражено
- Multi-tenant enforcement через middleware + dependency guard.
- RBAC/ABAC: `abac(...)` guards на маршрутах.
- Идемпотентность: `IdempotencyService`, ключи `Idempotency-Key` в критичных POST.
- Audit endpoints и audit service.
- Outbox/webhooks есть в API и сервисах.
- Client portal реализован отдельными backend+frontend модулями.

## 8) Что отсутствует/частично
- Полная ABAC-матрица на все роли/действия требует дополнительной верификации (частично покрыто).
- Не все блоки ТЗ имеют равномерное покрытие интеграционными тестами (особенно end-to-end cross-domain сценарии).
- PWA/offline и некоторые enterprise-блоки (CRM/finance deep link, billing глубина, backup/restore drills) реализованы частично.

## 9) Точки входа для запуска/проверки
- `make dev-lite`, `make test-lite`, `make run`, `make migrate`, `make pilot-smoke`, `make final-acceptance`.
- Frontend: `cd frontend && npm run dev|test|lint|build`.

## 10) Опасные неизвестности / техдолг
- Есть нестабильность части idempotency/packs тестов (обнаружен 500 на `POST /api/v1/packs/run` в определённом тест-кейсе).
- Есть исторические предупреждения SQLAlchemy relationships (overlaps), требующие рефакторинга модели.
- Часть проверок безопасности и pipeline-state проверяется фрагментарно по отдельным наборам тестов; нужна консолидация smoke/critical suite.
