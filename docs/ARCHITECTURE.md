# Архитектура платформы управления ОТ/ПБ/ПромБез

## Краткое описание
- **Назначение**: мультиарендный backend на FastAPI (`app/`) для управления компаниями, сотрудниками, документами, пакетами нормативных актов, оценками рисков и аудиторскими событиями.
- **Технологии**: FastAPI + SQLAlchemy 2.0 + PostgreSQL, Celery + Redis, MinIO/S3, DocxTPL + LibreOffice, Prometheus/OTel, ClamAV.
- **Слои**: API (`app/api`), бизнес-сервисы (`app/services`, `app/domains`), модели и БД (`app/models`, `app/db`), инфраструктура (`app/core`, `app/middleware`, `config/`).

## Доменные модули
| Домен | Модели (`app/models`) | Схемы (`app/schemas`) | API (`app/api/...`) | Сервисы/домены |
| --- | --- | --- | --- | --- |
| **Tenant & Auth** | `models.py::Tenant`, `User`, `ApiKey` | `tenant.py::TenantRead/TenantPage` | `api/routes/auth.py`, `api/v1/router.py` (`/tenants`) | `services/auth.py`, `services/api_keys.py`, `core/security.py` |
| **Компании и площадки** | `models.py::Company`, `Site`, `Position` | `company.py::CompanyCreate/Read/Page` | `api/v1/router.py` (`/companies`, `/sites`), вспомогательные проверки в `api/routes/packs.py` | `repository.py::create_company/list_companies`, `domains/packs/context.py` |
| **Персонал** | `models.py::Person`, `EmploymentStatus`, `PlanTask` | `person.py::PersonPage`, `task.py::PlanTaskRead` | `api/v1/router.py` (`/employees`), контекст для `documents`/`packs` | `repository.py::list_persons`, `services/tasks.py` |
| **Шаблоны** | `models.py::Template`, `TemplateVersion`, `TemplateVersionStatus` | `template.py::TemplateCreate`, `common.py::TemplatePage` | `api/v1/router.py` (`/templates`, загрузка DOCX) | `services/docx.py`, `services/file_storage.py`, `services/pipeline.py` |
| **Документы** | `document.py::Document`, `DocumentVersion`, `DocumentGenerationJob` | `document.py::DocumentRead`, `DocumentStatusUpdate` | `api/routes/documents.py` | `services/documents.py`, `services/docx.py`, `services/pdf.py`, `services/idempotency.py`, `services/tasks.py` |
| **Пакеты** | `models.py::DocumentPack`, `DocumentPackItem`, `DocumentPackScenario`, `PackageProfile`, `PackagePreset` | `pack.py::PackGenerateRequest/Response`, `PackListResponse` | `api/routes/packs.py` | `services/package_export.py`, `services/pipeline.py`, `services/file_storage.py`, `services/tasks.py`, `domains/packs/*` |
| **Файлы/хранилище** | `file.py::File`, `FileScanStatus` | Inline-схемы `FileUploadResponse`/`FileDownloadResponse` в `api/routes/files.py` | `api/routes/files.py` | `services/file_storage.py`, `domains/files/s3.py`, `services/storage.py`, `services/clamav.py`, `services/audit.py` |
| **Риски** | `risk.py::Risk`, `RiskHazard`, `RiskControl`, `RiskAssessment`, `RiskMatrixCell` | `risk.py::RiskListResponse`, input-модели в `api/routes/risk.py` | `api/routes/risk.py` | `services/risk.py`, `domains/risk/score_band.py` |
| **НПА** | `npa.py::NpaAct`, `NpaClause` | `npa.py::NpaActRead`, `NpaActListResponse` | `api/routes/npa.py` | `domains/npa/*` (загрузчики, миграции) |
| **Пайплайны/задачи** | `models.py::PipelineRun`, `PipelineRunStatus`, `Outbox` | `common.py::PipelineRunRead`, `task.py::TaskStatusResponse` | `api/routes/tasks.py`, части `api/routes/documents.py`, `api/routes/packs.py` | `services/tasks.py`, `services/pipeline.py`, `services/outbox.py`, `services/celery_app.py` |
| **Аудит** | `models.py::AuditLog`, `JournalEntry` | Inline `AuditLogEntry`/`AuditLogHistory` (`api/routes/audit.py`) | `api/routes/audit.py`, аудит в `files.py`, `documents.py`, `packs.py` | `services/audit.py`, `domains/audit/*` |

### Детализация доменов
- **Tenant/Auth**: зависимости `app/api/dependencies.py` инжектируют `AsyncSession` и выбранный `Tenant`. RBAC/ABAC (`app/core/security.py`) проверяет роли (`admin`, `employee`, `client_admin`, `client_user`). `services/auth.py` управляет паролями, JWT (`issue_access_token/refresh_token`).
- **Документы**: `/api/v1/documents` принимает `DocGenerateRequest`, валидирует шаблон/компанию/персону, контролирует ограничения payload (`core/payload_constraints.py`), рассчитывает `idempotency_key` (`core/idempotency.py`, `services/idempotency.py`) и запускает пайплайн через `tasks.generate_document_task`. `DocumentWorkflowService` в `services/documents.py` управляет статусами и аудитом.
- **Пакеты**: `api/routes/packs.py` аггрегирует данные компаний, площадок, сотрудников, медосмотров (`MedicalExam`), тренингов (`Training`) и генерирует документы пачками. Контекст формируется в `domains/packs/context.py`, экспорт упаковывается `PackageExportService` и сохраняется через `FileStorageService`.
- **Файлы**: `api/routes/files.py` применяет rate limit (`core/rate_limit.py`), определяет MIME (`domains/files/utils.py`), пишет метаданные `File`, инициирует ClamAV-сканирование (`services/clamav.py`) и логирует аудит (`AuditService`). Загрузка/выгрузка работает поверх `domains/files/s3.py` и `services/storage.py`.
- **Риски**: эндпоинты `/api/v1/risk/...` управляют словарями опасностей/мер, матрицами риска и оценками (`RiskAssessment`). `RiskService` рассчитывает уровни и отчёт по площадке, а модуль `domains/risk/score_band.py` определяет цветовые диапазоны.
- **НПА**: `/api/v1/npa` читает `NpaAct` вместе с `NpaClause` (selectinload). Эти данные используются шаблонами/пакетами, но не изменяются через API.
- **Пайплайны/задачи**: `PipelineService` связывает шаблоны, DocxTPL и конверсию в PDF, пишет `PipelineRun`. Celery-таски (`services/tasks.py`) мониторятся через `/api/v1/tasks/{id}` с агрегацией статуса Celery + `PipelineRun`. Idempotency и `PipelineRun` позволяют безопасно повторять генерацию.
- **Аудит**: `AuditService` сохраняет каждое критичное действие (загрузка файлов, смена статуса документа, запуск пакета). Запрос `/api/v1/audit` отдаёт историю по объекту.

## Логическая схема
1. **Tenant → Company → Person**: Tenant владеет компаниями (`Company.tenant_id`), каждая компания имеет площадки (`Site`) и сотрудников (`Person`, `PlanTask`).
2. **Template → Document → File**: шаблоны (`Template`, `TemplateVersion`) применяются к данным компании/персоны, создают `Document` с версиями и файлами (`File`, `storage_key`).
3. **Pack → DocumentGenerationJob → PipelineRun**: пакеты (`DocumentPack*`) формируют серию `DocumentGenerationJob`, которые превращаются в `PipelineRun`. Выполнение идёт в Celery, результат загружается в S3 и хранится в `File`, а статусы/metadata доступны через `/tasks` и `/packs`.
4. **Risk**: справочники опасностей/мер + матрица уровня риска используются для `RiskAssessment`, связанной с компанией и площадкой. `RiskService` агрегирует показатели для UI/отчётов.
5. **NPA**: глобальные акты (`NpaAct`) подключаются к шаблонам через ссылки/clauses и синхронизируются миграциями.
6. **Files ↔ ClamAV**: загрузки хранятся в MinIO (`domains/files/s3.py`), пока не пройдут ClamAV. `File.scan_status` обновляется задачами и определяет доступность скачивания.
7. **Audit**: `AuditLog` связывает `Tenant`, `User`, тип объекта и IP. Любая бизнес-операция вызывает `AuditService.log_event`.
8. **Idempotency/Outbox**: `DocumentGenerationJob.idempotency_key` и `services/idempotency.py` предотвращают дубликаты, `services/outbox.py` обеспечивает доставку событий (например, оповещения о генерации) в другие системы.

## Слои приложения
### API (`app/api`)
- `app/api/app.py` создаёт FastAPI-приложение, настраивает middleware (`TrustedHost`, `CORSMiddleware`, `TenantMiddleware`, `SlowAPIMiddleware`, `ObservabilityMiddleware`) и endpoint `/metrics` (Prometheus).
- `app/api/v1/router.py` агрегирует все доменные роутеры (`auth`, `audit`, `files`, `packs`, `npa`, `risk`, `documents`, `tasks`) и содержит дополнительные эндпоинты (`/companies`, `/employees`, `/templates`).
- `app/api/routes/*.py` содержат изолированные доменные контроллеры. Общие зависимости (`AsyncSession`, `Tenant`, `AccessContext`) — в `app/api/dependencies.py` и `app/api/deps/*`.

### Сервисный слой (`app/services`, `app/domains`)
- Доменные сервисы: `DocumentWorkflowService`, `PackageExportService`, `RiskService`, `AuditService`, `FileStorageService`, `DocxService`, `PipelineService`, `IdempotencyService`, `OutboxService`.
- Инфраструктура: `services/storage.py`/`domains/files/s3.py` (S3/MinIO), `services/clamav.py` (сканирование), `services/redis` (через Celery), `services/api_keys.py`, `services/auth.py`.
- Asynchronous execution: `services/celery_app.py` описывает Celery-инстанс, `services/tasks.py` регистрирует задачи `pipeline.run` и `documents.generate`.

### Модели и доступ к БД (`app/models`, `app/db`)
- `models/base.py` и `db/base.py` предоставляют `TenantBaseModel`, `SharedModel`, mixin soft delete и версионность.
- Сущности распределены по файлам: `models/models.py` (tenant, company, person, шаблоны, pipeline, пакеты), `models/document.py`, `models/file.py`, `models/risk.py`, `models/npa.py`, `models/checks.py`.
- `app/db/session.py` и `app/db/base.py` создают engine/Session, учитывают tenant при подключении. Репозитории (`app/repository.py`) агрегируют сложные SELECT’ы.

### Конфигурация и инфраструктура (`app/core`, `app/middleware`)
- `core/config.py` валидирует `.env`, управляет путями OpenAPI (`settings.api_v1_prefix/openapi.json`).
- Безопасность и управление доступом: `core/security.py`, `core/rate_limit.py`, `core/idempotency.py`, `core/payload_constraints.py`.
- Наблюдаемость: `core/logging.py`, `core/logging_config.py`, `core/metrics.py`, `core/tracing.py`, `middleware/observability.py`.
- Multitenancy и контекст: `core/tenant.py`, `middleware/tenant.py`, `core/task_context.py`.
- Ответы/фильтрация: `core/response.py`, `core/query.py`.

## OpenAPI
- Актуальная спецификация экспортирована в [`docs/openapi_snapshot_v01.json`](openapi_snapshot_v01.json) через `FastAPI().openapi()`. Файл фиксирует публичный контракт (`/health`, `/metrics`, `/api/v1/...`) и используется для регрессионных тестов.
- Эндпоинты для auth/files/documents/packs/risk/npa/tasks/companies/persons/templates включены в snapshot; при изменении API необходимо переснимать файл.

## Рекомендации по развитию
1. **Новые домены** — создавайте модели/схемы, сервисы, отдельный роутер и подключайте его в `app/api/v1/router.py`.
2. **API-изменения** — обновляйте pydantic-схемы, документируйте их в `docs/ARCHITECTURE.md`, снимайте новый OpenAPI snapshot.
3. **Фоновые процессы** — расширяйте Celery через `services/tasks.py`, логируйте метрики (`core/metrics`) и аудит.
4. **Наблюдаемость/безопасность** — используйте idempotency, rate limiters и аудит для всех операций записи.
