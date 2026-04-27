# ЕДИНОЕ ПОЛНОЕ ТЗ (Unified)

**По умолчанию для фразы «продолжай по ТЗ» без указания файла:** этот документ задаёт объём и приёмку (в паре с `docs/spec/README.md` → раздел «Если в задаче сказано „по ТЗ“»). Продуктовый vNext-спек и общая дорожная карта — в `PLATFORM_VNEXT_UPGRADE_SPEC.md` (для кода — инженерные правила: разд. 36 / `product_spec.py`).

Источник: пользовательское единое ТЗ из задачи «ДОДЕЛАТЬ ПРОЕКТ ПО ЕДИНОМУ ПОЛНОМУ ТЗ + НАВЕСТИ ПОРЯДОК В РЕПОЗИТОРИИ (BACKEND/FRONTEND/TESTS/DOCS/DEVX)».

## Оглавление
- [0) Обязательные артефакты в репозитории](#0-обязательные-артефакты-в-репозитории)
- [1) Baseline проверка и fail-first отчёт](#1-baseline-проверка-и-fail-first-отчёт)
- [2) P0: критические требования ТЗ](#2-p0-критические-требования-тз)
- [3) P1: MVP домены и пакеты](#3-p1-mvp-домены-и-пакеты)
- [4) Frontend: F1..F4](#4-frontend-f1f4)
- [5) DevX для новичка + test discovery](#5-devx-для-новичка--test-discovery)
- [6) Репозиторный hygiene](#6-репозиторный-hygiene)
- [7) Критерии приёмки](#7-критерии-приёмки)
- [Финальный отчёт в PR](#финальный-отчёт-в-pr)

## 0) Обязательные артефакты в репозитории

### 0.1 Сохрани ТЗ в репо [MVP]
- создать `docs/spec/TZ_FULL_UNIFIED.md` и перенести туда ТЗ пользователя (0–32 + Backend B1..B5 + Frontend F1..F4) без урезаний. [MVP]
- добавить оглавление и якоря. [MVP]
- пометить каждое требование тегом: [MVP] / [v1.1] / [v1.2] / [v2.0]. [MVP]

### 0.2 Создай матрицу покрытия ТЗ [MVP]
- `docs/audit/TZ_COVERAGE_MATRIX.md` с колонками:
  - REQ-ID
  - Требование
  - Backend (модуль/файлы/эндпоинты)
  - DB (таблицы/миграции)
  - Jobs (Celery)
  - Events (outbox/webhooks)
  - Frontend (экраны/фичи)
  - Tests
  - Status (OK/Partial/Missing)
  - Priority (P0/P1/P2)
  - Plan

### 0.3 Обнови README [MVP]
- “Quick start (Codespaces)” — минимальный путь запуска. [MVP]
- ссылки на `TZ_FULL_UNIFIED.md` и `TZ_COVERAGE_MATRIX.md`. [MVP]
- “как зайти в систему для тестов” через env bootstrap без секретов. [MVP]

### Acceptance 0 [MVP]
- `docs/spec/TZ_FULL_UNIFIED.md` существует и полный.
- `docs/audit/TZ_COVERAGE_MATRIX.md` заполнен минимум для MVP и критериев приёмки.
- README содержит рабочий быстрый старт и ссылки.

## 1) Baseline проверка и fail-first отчёт

### 1.1 В чистом Codespace выполнить [MVP]
- `make cs:reset`
- `cp .env.example .env`
- `make cs:dev`
- `make cs:test`
- backend: `source .venv/bin/activate && pytest --collect-only -q`
- frontend: `npm --prefix frontend test`

### 1.2 Зафиксировать результаты [MVP]
- `docs/audit/BASELINE_VERIFICATION.md` (что работает/не работает/ошибки/воспроизведение).

### Acceptance 1 [MVP]
- документ с baseline и воспроизводимостью есть.

## 2) P0: критические требования ТЗ

### 2.1 Мультиарендность / X-Tenant (TZ §1.1) [MVP]
- любой бизнес-роут без `X-Tenant` → 400.
- schema-per-tenant: middleware выставляет `search_path`.
- tenant scope обязателен в репозиториях/ORM фильтрах.
- файловая изоляция: S3 prefix `tenant/{tenant_id}/...`.
- Тест: `tests/test_tenant_header_required.py` должен проходить.

### 2.2 RBAC + ABAC и роли (TZ §1.2–1.3) [MVP]
- роли: полный список из ТЗ в модели/справочнике.
- ABAC атрибуты: company_id, site_id, document_id, status, risk_level, project_id, contractor_id.
- единый policy engine и унификация проверок.
- where-фильтры по scope (site/company).
- Тест: минимум 2 allow/deny на разные домены.

### 2.3 Аудит immutable + field-level diff (TZ §1.4) [MVP]
- AuditLog append-only (запрет UPDATE/DELETE на ORM + желательно DB).
- who/when/ip/ua/correlation-id + field diff.
- аудит атомарен с бизнес-операцией.
- Тест: update/delete audit → ошибка; бизнес-операции пишут audit.

### 2.4 Идемпотентность (TZ §12.1, B4, §32) [MVP]
- `idempotency_keys` с tenant_id, key, endpoint, request_hash, response_payload, created_at.
- повтор запроса:
  - одинаковый hash → тот же результат,
  - другой hash → 409.
- KPI-тест: повтор POST `/documents:generate` с тем же key возвращает тот же `document_version_id`.

### 2.5 Templates strict (TZ §2, §3.1, §32) [MVP]
- выбор строго по `(code, version)`.
- уникальность `(code, version)`.
- delete in-use → 409.
- KPI-тест: delete guard 409.

### 2.6 Outbox + dispatcher + retries + poison queue + metrics (TZ §12.3, B5) [MVP]
- `outbox_events`: status/attempts/next_retry_at/event_id/dedup.
- dispatcher worker: retries/backoff, dead-letter после max_attempts, Prometheus метрики.
- webhook routing: global + per-tenant subscriptions.
- KPI-тест: мок-приёмник + доставку/ретраи.

### 2.7 Обязательные события (TZ §12.2) [MVP]
- обязателен эмит:
  - DocumentGenerated
  - Signed
  - Exported
  - RiskAssessed
  - PPEIssued
  - TrainingCompleted
- Тест минимум для 3 событий: запись в outbox + dispatch.

### 2.8 Pipeline шаги (TZ §0.2, §3.4, B3) [MVP]
- этапы пайплайна как отдельные шаги со статусом/логом/ретраями.
- модель `DocumentJob` + шаги: template → headers → replace → pdf → zip → (sign/edo) → archive.
- timings, attempts, error_code/error_payload.
- Тест: pipeline smoke + статусы шагов.

### 2.9 Replace engine (TZ §3.3, §32) [MVP]
- dry-run report (CSV/JSON).
- diff preview (структура для UI).
- apply меняет body/tables/hdr/ftr; shapes/textboxes допускается [v1.1], но явно.
- backup + rollback обязателен.
- KPI-тест: dry-run/apply/rollback.

### 2.10 PDF + встроенные шрифты (TZ §3.1, §32) [MVP]
- LO headless pool для prod; dev fallback — feature flag.
- встройка шрифтов (DejaVu/Noto Sans).
- если не готово: явный TODO [v1.1] в матрице + skip-тест с причиной.

## 3) P1: MVP домены и пакеты

### 3.1 Риски (TZ §6) [MVP]
- PxS методика + hazards/measures.
- risk map сотрудника/места/объекта.
- план мер + контроль сроков.
- deterministic output.
- событие RiskAssessed → outbox.

### 3.2 СИЗ + склад (TZ §7) [MVP]/[v1.1]
- нормы СИЗ + карточки + журнал выдачи/возврата. [MVP]
- PPEIssued → outbox. [MVP]
- склад (остатки/партии/сертификаты/инвентаризация) — skeleton. [v1.1]

### 3.3 Обучение/инструктажи (TZ §8) [MVP]
- реестр программ/курсов/групп.
- тесты/протоколы/удостоверения (через documents pipeline).
- электронные журналы инструктажей (минимум).
- TrainingCompleted → outbox.

### 3.4 Инциденты/проверки/предписания (TZ §9) [MVP]/[v1.2]
- инциденты: регистрация + расследование + КД + сроки. [MVP]
- проверки: план/чек-листы минимум. [MVP]
- предписания skeleton. [v1.2]
- пакет “подготовка к проверке” MVP skeleton. [MVP]

### 3.5 Пакеты (§31) [MVP]
- “Выход на объект”.
- “Несчастный случай”.
- “Подготовка к проверке”.
- “Обучение”.
- Тест: 1–2 интеграционных сценария + фикстуры.

## 4) Frontend: F1..F4

### 4.1 Структура feature-based [MVP]
- `/features`: documents, risk, ppe, training, incidents, admin, client-cabinet.
- shared: api client, tenant context, auth, ui components, utils.
- слои entities/widgets/pages/app.

### 4.2 Обязательные экраны MVP [MVP]
- Login + Tenant selection.
- Dashboard KPI.
- Documents: templates list, generation wizard, job timeline, replace dry-run/diff/apply/rollback.
- Risks, PPE, Training, Incidents, Admin, Client cabinet v1.

### 4.3 UX-компоненты (TZ §25.2) [MVP]
- diff viewer.
- job timeline.
- поиск/фильтры.
- RBAC guard для действий/маршрутов.
- bulk actions (минимум).

### 4.4 Front tests [MVP]
- vitest smoke:
  - app renders,
  - tenant guard flows,
  - key routes render without crash.

## 5) DevX для новичка + test discovery

### 5.1 Каноничные команды [MVP]
- `make cs:reset`
- `make cs:dev`
- `make cs:test`

### 5.2 Dev-вход без секретов [MVP]
- bootstrap admin через env:
  - `ADMIN_BOOTSTRAP=1`
  - `ADMIN_EMAIL`
  - `ADMIN_PASSWORD`
  - `ADMIN_TENANT`
- документация: где задать и как зайти.

### 5.3 Test discovery [MVP]
- VS Code видит pytest (Testing panel):
  - interpreter = `.venv`
  - корректные `pytestArgs`
- при необходимости `scripts/pytest.sh`.

## 6) Репозиторный hygiene

### 6.1 Целевой порядок [MVP]
- единый путь установки/запуска.
- единый `.env.example` + docs.
- объединённый “правдивый” runbook.
- удаление мусора только после usage-check и зелёных тестов.

### 6.2 Что обязательно описать [MVP]
- `docs/repo-structure.md`.
- `docs/troubleshooting.md`.

### 6.3 CI/линтеры [MVP]/[v1.1]
- ruff/black/mypy, eslint/tsc не ломают разработку. [MVP]
- coverage gate core/domain/services ≥ 85%; если не достигнуто — план подъёма. [v1.1]

## 7) Критерии приёмки

В чистом Codespace:
1. `make cs:reset` [MVP]
2. `cp .env.example .env` + `ADMIN_BOOTSTRAP=1` [MVP]
3. `make cs:dev` (backend+frontend) [MVP]
4. В UI:
   - documents:generate (idempotency),
   - replace dry-run/apply/rollback,
   - risk assessment (deterministic),
   - PPE issue (PPEIssued),
   - training completion (TrainingCompleted). [MVP]
5. `make cs:test` зелёный [MVP]
6. Тесты видны в VS Code Testing panel [MVP]
7. docs/spec + docs/audit и ссылки в README [MVP]

## Финальный отчёт в PR
- Краткое резюме: сколько требований [MVP] OK/Partial/Missing. [MVP]
- Список P0/P1/P2 и что сделано. [MVP]
- Список изменённых файлов/директорий и почему. [MVP]
- Команды запуска/тестов (как в README). [MVP]
- Отложено на [v1.1]/[v1.2]/[v2.0] только реалистичное. [MVP]

## Backend B1..B5 и Frontend F1..F4 (фиксация)
- **B1**: tenant isolation + scoped access. [MVP]
- **B2**: RBAC/ABAC policy enforcement. [MVP]
- **B3**: document pipeline step orchestration. [MVP]
- **B4**: idempotency keys and replay semantics. [MVP]
- **B5**: outbox/webhooks delivery guarantees. [MVP]
- **F1**: feature-based frontend structure. [MVP]
- **F2**: обязательные MVP экраны. [MVP]
- **F3**: UX components (diff/timeline/filter/guards). [MVP]
- **F4**: frontend smoke tests. [MVP]

> Примечание: по источнику задачи упоминаются ссылки на §0–32, но в предоставленном тексте детально раскрыты блоки 0–7 и B1..B5/F1..F4; именно они зафиксированы здесь без сокращения формулировок.
