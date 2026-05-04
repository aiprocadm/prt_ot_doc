# Repo quick facts and debts

> **DEPRECATED (2026-05-04, snapshot of an early wave).** Этот файл — рабочий снимок ранней волны и **не отражает текущего состояния** (часть указанных «недоделок» давно закрыта: domains, модели, security middleware, S3/MinIO, тесты, миграции). Не использовать для приёмки/планирования.
>
> Актуальные источники:
> - **ТЗ:** [`spec/TZ_FULL_UNIFIED.md`](spec/TZ_FULL_UNIFIED.md).
> - **Текущее состояние:** [`../AI_IMPLEMENTATION_REPORT.md`](../AI_IMPLEMENTATION_REPORT.md) (последний handoff) + [`audit/TZ_COVERAGE_MATRIX.md`](audit/TZ_COVERAGE_MATRIX.md).
> - **Открытые блокеры:** [`../GAP_REPORT.md`](../GAP_REPORT.md) + [`stabilization/RELEASE_BLOCKERS_STATUS.md`](stabilization/RELEASE_BLOCKERS_STATUS.md).
> - **Архитектура:** [`ARCHITECTURE.md`](ARCHITECTURE.md), [`MODULES.md`](MODULES.md).
>
> Кандидат на удаление в Wave 4 cleanup (см. [`CLEANUP_CANDIDATES.md`](CLEANUP_CANDIDATES.md)).

- FastAPI backend present with modular layout under `backend/app/` (api, core, db, domains, models, schemas, services).
- Multi-tenant DB session implemented in `backend/app/db/session.py` with optional per-tenant schemas; async SQLAlchemy 2.x used.
- Alembic configured; at least two migration scripts exist (`20240408_0001...`, `20240709_0002...`).
- Dockerfile and docker-compose exist; compose spins Postgres, Redis, MinIO, backend, frontend, and a reverse proxy.
- Celery worker scaffolding present (`backend/app/tasks.py`, `backend/app/worker.py`) with Redis broker configured via settings.
- Settings managed via pydantic-settings; JWT config fields (issuer, audience, algorithm, TTL) are defined.
- Domain stubs exist: `templating/renderer.py`, `replace/engine.py`, `files/document.py`, `packs/service.py`, `npa/compliance.py`; они минимальны и требуют доработки.
- API v1 router реализует базовые эндпоинты (tenants, companies, employees, templates, docx helpers, pipeline execution); остальной контракт в `docs/openapi.yaml` пока не реализован.
- Models module определяет ключевые сущности (Company, Position, Person, Template, Document, Pack, PPEIssue, AuditLog и др.), но отсутствуют многие таблицы из ERD (`docs/erd.puml`).
- MinIO S3 storage объявлен в compose; `services/file_storage.py` пока работает в памяти и нуждается в реальной интеграции с S3/ClamAV.
- Security module существует; JWT и CORS/TrustedHost middleware настроены, но не применяются на маршрутах.
- Тесты лежат в `tests/`; покрытие частичное, часть сценариев отсутствует. Предыдущие прогоны падали из-за несовместимости ключей покрытия.
- CI workflow обнаружен (`.github/workflows/ci.yml`), собирает контейнер и запускает линтеры/тесты, но не публикует OpenAPI/ERD артефакты.
- Makefile содержит цели `install`, `lint`, `format`, `test`, `run`, `build`, `clean`; миграции/seed/compose нужно добавить.
- Документация приведена к единой правде: `docs/spec/TZ_FULL_UNIFIED.md` (ТЗ), `docs/erd.puml` (ERD), `docs/openapi.yaml` (контракт), `docs/spec_compliance_report.md` (отчёт).
