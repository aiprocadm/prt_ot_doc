# Backend Technical Specification — PRT OT DOC

Версия: v2.1 • Дата: 2025-11-05 • Репозиторий: https://github.com/alexkarpov772/prt_ot_doc

Этот документ заменяет все предыдущие вариации `Backend_TZ*.md` и фиксирует единственную актуальную версию бэкенд-ТЗ.

## 0. Executive summary
- **Цель.** Единый многоарендный backend, закрывающий учёт компаний, людей, обучения, СИЗ, проверок, документов и рисков. Сервис выдаёт документы и отчёты из шаблонов, уведомляет внешние системы и ведёт аудит.
- **Объём.** REST API (`/api/v1`), фоновые очереди, PostgreSQL схема, MinIO файловое хранилище, Redis, Celery, OpenTelemetry, CI/CD, миграции Alembic и тесты.
- **Ограничения.** Сохранить обратную совместимость публичных HTTP-эндпоинтов, входящих в контракт `docs/openapi.yaml`. Генерация тяжёлых файлов строго асинхронно через очереди. Все сервисы контейнеризованы и запускаются через `docker compose`.
- **Допущения.** *Фронтенд и внешние клиенты авторизуются через JWT (OIDC issuer). Критичные внешние интеграции (1С, ФРДО, ЕИСОТ) принимают вебхуки с повтором по экспоненте.*

## 1. Архитектура
### 1.1 Runtime overview
- **Фреймворк.** FastAPI + SQLAlchemy 2.0 (async). Конфигурация через Pydantic Settings, `.env` валидируется на запуске.
- **Сервисные процессы.**
  1. HTTP-приложение (Uvicorn/Gunicorn) обслуживает REST.
  2. Celery workers (`documents`, `reports`, `integrations`) выполняют тяжёлые задачи, используют Redis как broker/result backend.
  3. Beat планирует ретраи и отложенные пайплайны.
- **Хранилища.** PostgreSQL 15 (multi-tenant), MinIO S3 (версии файлов), Redis (кэш и очереди). Все доступы по TLS, секреты — только из переменных окружения/secret manager.
- **Observability.** OTEL-экспорт метрик/трейсов, JSON-логи со `trace_id` и `tenant_id`, healthchecks `/healthz`, `/readyz`, `/metrics`.

### 1.2 Request lifecycle
1. Reverse proxy проверяет TLS и прокидывает заголовки `X-Request-Id`, `X-Tenant-Id`.
2. FastAPI middleware валидирует аренду и открывает tenant-scoped сессию БД.
3. Контроллер выполняет Pydantic-валидацию, обращается к доменному сервису.
4. Доменный сервис использует репозиторий в транзакции, обновляет агрегаты, пишет `audit_log` и `webhook_outbox`.
5. По завершении фиксируется транзакция, Celery job публикуется в нужную очередь, ответ возвращается в формате `Envelope`.

### 1.3 Component responsibilities
- `backend/app/api` — HTTP-слой, аутентификация, авторизация (RBAC/ABAC), маппинг DTO.
- `backend/app/domains/*` — предметные сервисы (companies, people, templates, ppe, inspections, incidents, risk, npa, packs, documents).
- `backend/app/services` — инфраструктурные обвязки: Celery, MinIO, ClamAV, LibreOffice pool, idempotency, webhooks.
- `backend/app/repository.py` — единая точка доступа к транзакциям, Unit of Work + outbox.
- `backend/app/models` — SQLAlchemy ORM (см. ERD в `docs/erd.puml`).
- `backend/app/tasks.py` + `worker/` — Celery entrypoints для генерации документов, паков, экспорта, синхронизации интеграций.
- `backend/app/core` — конфигурация, логирование, трассировка, security helpers.

### 1.4 Integrations & flows
- **Документы.** DOCX шаблоны в MinIO → рендеринг LibreOffice → PDF + ZIP → подписи webhooks.
- **Packs.** Сценарии запускают несколько шаблонов/отчётов, агрегируют статус в `document_job`.
- **Инциденты/проверки.** Чекап чек-листов, загрузка фото (MinIO), план корректирующих действий.
- **Внешние системы.** Outbox → Celery `integrations` → HTTP webhook + повтор с backoff. Поддержка фидов 1С/ФРДО/ЕИСОТ.
- **Оплата/лимиты.** Таблицы `billing_subscription`, `feature_enablement` включают тарифы и ограничители на уровне аренды.

## 2. Domain model
- Multi-tenant: каждая таблица (кроме справочников) содержит `tenant_id`, схема описана в `docs/erd.puml`.
- Основные агрегаты:
  - **Companies/Sites/People.** Учет юрлиц, площадок, персонала, связка с СИЗ, обучением, медосмотрами, допусками.
  - **Templates/Documents/Packs.** Управление версиями шаблонов, пайплайны генерации, хранение результатов.
  - **Safety.** Чек-листы, проверки, нарушения, корректирующие действия, инциденты, риск-карты.
  - **Compliance.** НПА, привязки, аудит, подписанные файлы, webhook outbox.
  - **Platform.** Feature toggles, биллинг, подписки, пользователи и роли.
- Полный список сущностей, атрибутов и связей: `docs/erd.puml` (PlantUML ERD). Диаграмма синхронизирована с этим документом.

## 3. API contract
- Единый базовый путь: `/api/v1`. Авторизация — `Authorization: Bearer <token>`, обязательный заголовок `X-Tenant-Id`.
- Контракт зафиксирован в `docs/openapi.yaml` и покрывает:
  - Аутентификация (`POST /auth/login`).
  - Управление арендами и компаниями (`GET /tenants`, CRUD по компаниям и сотрудникам).
  - Шаблоны и версии (`/templates`, `/templates/{id}/versions`).
  - Операции над DOCX (`/docx/mass-replace`, `/docx/headers`).
  - Пайплайны и пакетная генерация (`/documents/*`, `/packs/run`, `/pipelines/{template_id}/run`).
  - Файловые операции (`/files/upload`, `/files/{id}/url`).
  - Мониторинг фоновых задач (`/pipelines/jobs/{id}`, `/documents/jobs/{id}`).
- Формат ответов — `Envelope { data, error, correlation_id }`. Ошибки — структурированные коды.
- Все изменяющие запросы требуют заголовка `Idempotency-Key` (минимум 8 символов).

## 4. Non-functional requirements
### 4.1 Security
- Обязательная аутентификация JWT, refresh flow, ротация ключей. RBAC (tenant roles) + ABAC (policy rules по объектам).
- Валидация всех входов: размер файлов, MIME sniffing, ClamAV, лимит загрузок.
- Secret Management через Vault/secret manager; секреты не хранятся в репозитории.
- Логи не содержат PII, кроме `trace_id` и `tenant_id`.

### 4.2 Reliability & operations
- Транзакции оборачивают бизнес-операции, `audit_log` и `webhook_outbox` пишутся атомарно.
- Ретраи Celery с экспонентой, dead-letter очереди, паузы при недоступности MinIO/PostgreSQL.
- Rate limiting per tenant, Circuit breaker на внешние сервисы, 504 timeout 30с на HTTP слое.

### 4.3 Performance & scalability
- Цель: P95 < 400 мс для чтений, P99 < 2 с для команд (без генерации файлов).
- Кэш Redis для справочников (TTL 5 минут) и публичных ключей.
- Масштабирование: горизонтальное (статeless API), worker autoscale по очередям.

### 4.4 Compliance & audit
- Полный аудит CRUD, хранение файлов версионно (`file_object.version_of`).
- Хранение документов минимум 5 лет, удаление — через политики S3 lifecycle.
- Соответствие ГОСТ по охране труда: хранение протоколов, обучение, PPE учёт.

## 5. Delivery, testing & quality
- CI: lint (`ruff`, `black --check`), типизация (`mypy`), тесты (`pytest --cov>=80`), сборка Docker.
- CD: GitHub Actions → staging → production. Миграции Alembic выполняются автоматически с возможностью отката.
- Тестовая пирамида: unit (фикстуры, мок-адаптеры), service (Testcontainers для Postgres/Redis/MinIO), contract (Schemathesis по `docs/openapi.yaml`), e2e (docker compose up + playwright).
- Мониторинг качества: SonarQube, Sentry, uptime checks.

## 6. Linked artifacts
- `docs/erd.puml` — ERD PlantUML синхронизирован с разделом 2.
- `docs/openapi.yaml` — OpenAPI 3.1 контракт для API.
- `docs/spec_compliance_report.md` — актуальный отчёт о соответствии кода требованиям.
- `docs/facts.md` — список фактов и долгов, обновляется по ревью.
