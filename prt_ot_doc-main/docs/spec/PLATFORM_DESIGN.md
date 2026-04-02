# PLATFORM DESIGN (Source of Truth)

## Оглавление
1. [Vision и архитектурный стиль](#vision-и-архитектурный-стиль)
2. [Bounded contexts и внутренние контракты](#bounded-contexts-и-внутренние-контракты)
3. [Multi-tenant: schema-per-tenant + X-Tenant](#multi-tenant-schema-per-tenant--x-tenant)
4. [Безопасность: Auth/JWT, RBAC + ABAC, immutable audit](#безопасность-authjwt-rbac--abac-immutable-audit)
5. [Documents Engine и pipeline](#documents-engine-и-pipeline)
6. [Outbox + Webhooks + retries/dead-letter/metrics](#outbox--webhooks--retriesdead-lettermetrics)
7. [Доменные модули MVP](#доменные-модули-mvp)
8. [Хранилище, PDF и антивирус](#хранилище-pdf-и-антивирус)
9. [Frontend архитектура (feature-based)](#frontend-архитектура-feature-based)
10. [DevX/Codespaces, качество и тесты](#devxcodespaces-качество-и-тесты)
11. [Roadmap и открытые риски](#roadmap-и-открытые-риски)

## Vision и архитектурный стиль
Платформа строится как **Modular Monolith**:
- единый deployable backend и единая БД;
- домены изолируются на уровне модулей, сервисов и контрактов;
- межмодульное взаимодействие — через публичные сервисные интерфейсы и события (Outbox), а не через хаотичные прямые импорты.

Цель: сохранить низкую операционную сложность MVP, но обеспечить эволюцию к распределённой архитектуре без переписывания бизнес-ядра.

## Bounded contexts и внутренние контракты
Целевые bounded contexts:
- **Core**: tenant, auth/security, audit, files, outbox, webhooks, feature flags, idempotency.
- **HR/Org**: tenants/companies/persons/sites/departments/roles.
- **Documents**: templates, versions, generate/render pipeline, package/export.
- **Risks**: hazards, assessment, PxS, карты и планы действий.
- **PPE/Warehouse (СИЗ/склад)**: нормы, выдача/возврат, журнал.
- **Training (Обучение)**: курсы/планы/сессии/завершение.
- **Incidents/Inspections (Инциденты/Проверки)**: инциденты, корректирующие действия, инспекции.
- **CRM/Billing**: skeleton (контуры сущностей и API без полной бизнес-логики).

Внутренний контракт модуля:
- `api/routes` — HTTP слой (валидация + orchestration);
- `services` — use-cases/бизнес-потоки;
- `repository`/`repos` — доступ к БД;
- `schemas` — DTO/контракты;
- `events` — доменные события для Outbox;
- `tasks` — async/background orchestration.

## Multi-tenant: schema-per-tenant + X-Tenant
Целевая модель изоляции:
- **schema-per-tenant** в production PostgreSQL;
- `X-Tenant` обязателен для `/api/v1/*` бизнес-роутов (кроме public health/auth);
- middleware должен выставлять tenant context и `search_path` в рамках запроса.

Текущий MVP-статус:
- в dockerless/Codespaces используется SQLite для onboarding;
- tenant enforcement реализуется заголовком `X-Tenant` и request-context;
- production-контур сохраняет направление на `search_path`-ориентированную изоляцию.

KPI-2: отсутствие `X-Tenant` на бизнес-роутах должно приводить к контролируемой ошибке (`tenant_required`).

## Безопасность: Auth/JWT, RBAC + ABAC, immutable audit
### Auth/JWT
MVP-подход:
- bearer JWT access token;
- tenant scope в claims;
- dev bootstrap admin для локального запуска.

Roadmap:
- refresh token rotation, revoke lists, session hardening.

### RBAC + ABAC
Политики доступа должны оцениваться единообразно через policy engine:
- `policy_engine.evaluate(user, action, resource, attrs) -> allow/deny + conditions`.

Минимальные требования:
- единый namespace action names между доменами;
- tenant boundary и company/resource ownership проверки на уровне ABAC.

### Immutable audit
Аудит — append-only:
- запись событий действий/изменений;
- запрет update/delete audit records;
- цепочка correlation/request metadata для трассировки.

## Documents Engine и pipeline
Поток генерации документов:
1. Template selection по `(template_code, version)`.
2. Render (hdr/ftr + replace engine).
3. Conversion DOCX→PDF.
4. Archive + публикация события.

Контрактные требования:
- **Idempotency-Key обязателен** на запуск pipeline/генерации (KPI-1).
- Удаление используемого template/version должно давать **409 Conflict** (KPI-3).
- `PipelineJob/PipelineTask` фиксируют status, progress, attempts, step timings, error.

Replace engine:
- минимум — поддержка **dry-run** с отчётом изменений;
- apply + rollback допускаются поэтапно (roadmap), но dry-run обязателен в спецификации.

PDF conversion:
- dockerless: допустим feature-flagged stub PDF;
- docker/full: LibreOffice headless pool/queue.

## Outbox + Webhooks + retries/dead-letter/metrics
События публикуются транзакционно через Outbox:
- запись события в той же транзакции, что и бизнес-операция;
- dispatcher с retries/backoff;
- dead-letter для исчерпанных попыток;
- metrics по очередям, попыткам, ошибкам, latency.

Webhook routing:
- глобальные и tenant-specific subscriptions;
- доставка с retry;
- HMAC подпись полезной нагрузки (MVP/roadmap в зависимости от окружения).

Ключевые события:
- `DocumentGenerated`, `DocumentSigned`, `DocumentExported`
- `RiskAssessed`
- `PPEIssued`
- `TrainingCompleted`

KPI-4: outbox/webhook контур проверяется тестами и ручным dev-сценарием.

## Доменные модули MVP
### Risks
- методика PxS (MVP), deterministic output для одинакового input (KPI-5).

### PPE / Warehouse (СИЗ/склад)
- нормы СИЗ;
- выдача/возврат;
- событие `PPEIssued`.

### Training (Обучение)
- фиксация завершения;
- событие `TrainingCompleted`.

### Incidents / Inspections
- инциденты: создание, corrective actions, сроки, обязательства/задачи;
- inspections: baseline skeleton + registry.

## Хранилище, PDF и антивирус
- S3/MinIO для объектного хранения артефактов и вложений.
- PDF conversion: LibreOffice headless pool.
- ClamAV интеграция — roadmap (включая policy на reject/quarantine и аудит).

## Frontend архитектура (feature-based)
Целевая структура:
- `src/app` (router/providers)
- `src/shared` (ui/api/hooks/utils)
- `src/entities`
- `src/features`
- `src/widgets`
- `src/pages`

UX-контракты:
- tenant picker / tenant context;
- API client inject `X-Tenant` на `/api/v1`;
- controlled UX при `tenant_required` (без white screen);
- стабильный dev login flow.

## DevX/Codespaces, качество и тесты
Канонические команды для новичка:
1. `make cs:reset`
2. `cp .env.example .env` + `ADMIN_BOOTSTRAP=1`
3. `make cs:dev`
4. login (tenant/email/password)
5. `make cs:test`

Качество:
- CI только проверяет (check-only), не вносит правки;
- pytest/vitest discovery должны работать из коробки;
- KPI-1..KPI-5 покрыты backend tests.

## Roadmap и открытые риски
- Полная schema-per-tenant в production + миграционные guardrails.
- Усиление policy engine (attribute sources, explicit deny tracing).
- Replace apply + transactional rollback.
- HMAC webhooks во всех каналах доставки.
- ClamAV обязательный в production-профиле.
- LibreOffice pool scaling + очереди + circuit breaker.
