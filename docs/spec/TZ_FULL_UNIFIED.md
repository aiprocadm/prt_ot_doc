# Единое полное ТЗ (OT/PB/Промбез/ЭКО + ЭДО)

> Статус: **единый source of truth по требованиям** для текущего репозитория.
> 
> Категории релизов: **MVP (обязательно)**, **v1.1 (важно)**, **v1.2 (позже)**, **v2.0 (позже)**.

## Оглавление
- [0. Цели и границы](#0-цели-и-границы)
- [1. Платформенные требования](#1-платформенные-требования)
  - [1.1 Tenant isolation](#11-tenant-isolation-mvp)
  - [1.2 RBAC](#12-rbac-mvp)
  - [1.3 ABAC](#13-abac-mvp)
  - [1.4 Audit log](#14-audit-log-mvp)
- [2. Шаблоны и версии](#2-шаблоны-и-версии-mvp)
- [3. Документный pipeline и replace](#3-документный-pipeline-и-replace)
- [4. KPI и acceptance](#4-kpi-и-acceptance-mvp)
- [5. Эксплуатация и DevX](#5-эксплуатация-и-devx)
- [6. Доменные модули MVP](#6-доменные-модули-mvp)
- [7. Backend спецификация (B1..B5)](#7-backend-спецификация-b1b5)
- [8. Frontend спецификация (F1..F4)](#8-frontend-спецификация-f1f4)
- [9. Roadmap и отложенные требования](#9-roadmap-и-отложенные-требования)
- [10. Контрольный список §0..§32](#10-контрольный-список-032)

## 0. Цели и границы
- Платформа охватывает OT/PB/Промбез/ЭКО процессы, документооборот и интеграции через API/events/webhooks. **(MVP)**
- Решение должно запускаться и тестироваться в GitHub Codespaces без Docker как основной сценарий новичка. **(MVP)**
- Полнота покрытия по требованиям проверяется через матрицу `docs/audit/TZ_COVERAGE_MATRIX.md`. **(MVP)**

## 1. Платформенные требования

### 1.1 Tenant isolation (MVP)
- Любой бизнес-роут без `X-Tenant` возвращает `400`.
- Middleware валидирует tenant и применяет schema search_path (schema-per-tenant).
- Хранилище файлов изолируется tenant-префиксом/бакетом.
- Очереди и лимиты минимум логически изолированы (`tenant_id` в payload + rate limits).

### 1.2 RBAC (MVP)
- Поддерживается полный каталог ролей, соответствующий ТЗ проекта.
- Проверки прав обязательны на уровне API.

### 1.3 ABAC (MVP)
- Атрибуты политик: `company_id`, `site_id`, `document_id`, `status`, `risk_level`, `project_id`, `contractor_id`.
- Политики применяются как на уровне доступа к endpoint, так и на уровне query-фильтров.
- Используется единый интерфейс Policy Engine.

### 1.4 Audit log (MVP)
- AuditLog append-only: запрещены `UPDATE/DELETE`.
- Содержит who/when/ip/ua/correlation-id + field-level diff.
- Аудит пишется атомарно с бизнес-операцией.

## 2. Шаблоны и версии (MVP)
- Выбор шаблона строгий по `(code, version)`.
- Уникальность `(code, version)` обязательна.
- Запрещено удаление версии, если она используется (`409`).

## 3. Документный pipeline и replace
- Модель job/шагов: `Template → Headers → Replace → PDF → (ZIP) → (EDO/Sign) → Archive`. **(MVP)**
- Для каждого шага: `status`, `started_at`, `ended_at`, `attempts`, `error_code`, `error_payload`. **(MVP)**
- Идемпотентность POST-операций через `idempotency_keys(tenant_id, key, endpoint, request_hash, response_payload, created_at)`. **(MVP)**
  - одинаковый hash: вернуть прежний ответ;
  - другой hash для того же key: `409`.
- Replace engine:
  - `dry-run` с отчётом попаданий (CSV/JSON) + diff preview;
  - `apply` для body/tables/hdr/ftr;
  - `rollback` batch;
  - нормализация runs. **(MVP)**
- Поддержка shapes/textboxes — **v1.1**, если не реализовано в текущем backend.
- PDF conversion: production target — LibreOffice headless pool. **(MVP контракт)**
- Проверка embedded fonts (кириллица) — **v1.1**, если инфраструктурно недоступно.

## 4. KPI и acceptance (MVP)
- Без `X-Tenant` → `400`.
- Idempotency generate: повтор с тем же key возвращает тот же `document_version_id`.
- Delete template in-use → `409`.
- Webhook dispatch (mock receiver) ≤ 60s.
- Risk deterministic (повторяемые расчеты).

## 5. Эксплуатация и DevX
- Health endpoints:
  - `/healthz` (liveness);
  - `/readyz` (readiness, включая зависимости/stub). **(MVP)**
- Codespaces runbook: reset → env → dev → login → tests. **(MVP)**
- Bootstrap admin из env допустим только для development/test режимов. **(MVP)**
- Никаких секретов в репозитории. **(MVP)**

## 6. Доменные модули MVP
- **Risk**: матрица `P×S`, справочники hazards/measures, карта рисков, план мер, deterministic KPI.
- **PPE**: нормы, выдача/возврат, журнал, событие `PPEIssued`.
- **Training/Briefings**: реестр, completion, событие `TrainingCompleted`, журналы инструктажей (минимум).
- **Incidents**: регистрация, КД, контроль сроков.
- **Inspections/Prescriptions**: минимум реестр, иначе roadmap v1.2 с согласованным скелетом.

## 7. Backend спецификация (B1..B5)

### B1. API и контракты (MVP)
- FastAPI API с tenant-aware middleware, auth, policy checks, audit hooks.
- Контрактные тесты и smoke health/readiness.

### B2. Данные и миграции (MVP)
- SQLAlchemy/Alembic схемы для доменов и служебных сущностей (idempotency/outbox/audit/pipeline).

### B3. Pipeline и рендеринг (MVP)
- Job orchestration, replace pipeline, pdf conversion contract, retries/errors.

### B4. Domain services (MVP)
- Risk/PPE/Training/Incidents бизнес-сервисы и события.

### B5. Outbox, delivery, observability (MVP)
- `outbox_events`: delivery guarantees, retry/backoff, poison/dead-letter, dedupe.
- Метрики Prometheus: delivered/failed/attempts/latency.
- Webhooks routing: global + per-tenant subscriptions; payload содержит `event_id` + `correlation-id`.
- HMAC подпись webhook — **v1.1** (контракт предусмотреть).

## 8. Frontend спецификация (F1..F4)

### F1. Архитектура и tenant context (MVP)
- Feature-based структура: `features/{documents,risk,ppe,training,incidents,admin}` + shared слои.
- Tenant обязателен в state и в заголовке `X-Tenant`.

### F2. Экраны MVP
- Login + Tenant selection
- Dashboard (минимальные KPI/просрочки)
- Documents (templates list + pipeline/job history)
- Replace (upload map + dry-run report + apply/rollback)
- Risks, PPE, Training, Incidents, Admin (минимально рабочие)

### F3. Guards и авторизация (MVP)
- RBAC/ABAC guard на маршрутах/действиях (минимум RBAC).

### F4. Тесты фронтенда (MVP)
- Vitest smoke: app render, tenant required flows, routing key pages.

## 9. Roadmap и отложенные требования
- **v1.1**: shapes/textboxes replacement, webhook HMAC signing, embedded fonts strict check.
- **v1.2**: расширенные inspections/prescriptions сценарии.
- **v2.0**: расширенный EDO/sign orchestration, enterprise integrations.

## 10. Контрольный список §0..§32
> Ниже — унифицированная ссылка требований с привязкой к реализации и приоритету.

- §0: Общая архитектура и единый pipeline — **MVP**
- §1: Tenant / RBAC / ABAC / Audit — **MVP**
- §2: Template versioning — **MVP**
- §3: Replace + PDF + pipeline steps — **MVP (+ v1.1 часть расширений)**
- §4–§5: KPI/acceptance — **MVP**
- §6–§9: Риски/СИЗ/обучение/инциденты — **MVP**
- §10–§11: Эксплуатация/health/readiness — **MVP**
- §12: Outbox + webhooks + retries — **MVP (+ HMAC v1.1)**
- §13–§24: Интеграции, наблюдаемость, операции — **MVP/P1 по матрице покрытия**
- §25: Frontend feature architecture — **MVP**
- §26–§30: UX/flows/tests — **MVP/P1**
- §31: Пакеты и доменные модули — **MVP**
- §32: Ключевые acceptance критерии и guardrails — **MVP**

Для точного статуса реализации см. матрицу покрытия: `docs/audit/TZ_COVERAGE_MATRIX.md`.
