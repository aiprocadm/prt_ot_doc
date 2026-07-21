# ЕДИНОЕ ПОЛНОЕ ТЗ ПЛАТФОРМЫ (Unified)

> **Этот документ — канонический и единственный источник истины для фразы «продолжай по ТЗ».**
> Ссылается на `docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md` (продуктовая рамка vNext, разделы 0–37) и на текущее состояние реализации (`AI_IMPLEMENTATION_REPORT.md`, `docs/audit/TZ_COVERAGE_MATRIX.md`). Не дублируйте требования в других файлах: при расхождениях побеждает этот файл, далее — `PLATFORM_VNEXT_UPGRADE_SPEC.md` (только в части продуктовой рамки и разд. 36 ограничений).

- **Версия:** 2026-05-04 (вторая редакция, согласована с PLATFORM_VNEXT_UPGRADE_SPEC.md разд. 0–37)
- **Статус:** активный
- **Канонические пути:** `backend/app/core/product_spec.py` (программные константы — `PLATFORM_VNEXT_UPGRADE_SPEC_PATH` + сжатые правила разд. 36), [`docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md`](./PLATFORM_VNEXT_UPGRADE_SPEC.md) (полный vNext-spec).

---

## Оглавление

- [0. Как читать этот документ и работать «по ТЗ»](#0-как-читать-этот-документ-и-работать-по-тз)
- [A. Объём и приёмка MVP (текущий релизный контур)](#a-объём-и-приёмка-mvp-текущий-релизный-контур)
  - [A.0 Обязательные артефакты в репозитории](#a0-обязательные-артефакты-в-репозитории)
  - [A.1 Baseline и fail-first отчёт](#a1-baseline-и-fail-first-отчёт)
  - [A.2 P0: критические требования](#a2-p0-критические-требования)
  - [A.3 P1: MVP домены и пакеты](#a3-p1-mvp-домены-и-пакеты)
  - [A.4 Frontend: F1..F4](#a4-frontend-f1f4)
  - [A.5 DevX и test discovery](#a5-devx-и-test-discovery)
  - [A.6 Репозиторный hygiene](#a6-репозиторный-hygiene)
  - [A.7 Критерии приёмки MVP](#a7-критерии-приёмки-mvp)
  - [A.8 Backend B1..B5 / Frontend F1..F4 (фиксация)](#a8-backend-b1b5--frontend-f1f4-фиксация)
- [B. Полный объём (vNext «эталонная платформа»)](#b-полный-объём-vnext-эталонная-платформа)
- [B-NEXT. Расширение объёма: аутсорсинг, модульность, UX, безопасность, эксплуатация](#b-next-расширение-объёма-аутсорсинг-модульность-ux-безопасность-эксплуатация)
- [C. Текущее состояние реализации (как зафиксировано)](#c-текущее-состояние-реализации-как-зафиксировано)
- [D. Дорожная карта реализации (фазы)](#d-дорожная-карта-реализации-фазы)
- [E. Обязательные правила доработки (разд. 36 vNext)](#e-обязательные-правила-доработки-разд-36-vnext)
- [F. Критерии приёмки по ключевым блокам (vNext §35)](#f-критерии-приёмки-по-ключевым-блокам-vnext-35)
- [G. Карта канонических документов и запрет на дубли](#g-карта-канонических-документов-и-запрет-на-дубли)
- [H. Финальный отчёт в PR (шаблон)](#h-финальный-отчёт-в-pr-шаблон)

---

## 0. Как читать этот документ и работать «по ТЗ»

### 0.1 Триада источников истины

При фразе **«продолжай по ТЗ»** агент или разработчик обязан опираться **только** на эти файлы (в указанном порядке):

1. `docs/spec/TZ_FULL_UNIFIED.md` — **этот файл**: объём, приёмка, MVP, полный объём, статус, фазы.
2. `AI_IMPLEMENTATION_REPORT.md` — журнал того, что уже сделано, какие есть ограничения, какой следующий шаг (handoff между волнами/агентами).
3. `docs/audit/TZ_COVERAGE_MATRIX.md` — матрица покрытия требований MVP (REQ-ID → backend / frontend / tests / status).

Дополнительные источники, которые **используются по запросу**, но не являются точкой входа:

- `docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md` — полная продуктовая рамка vNext (разделы 0–37), конкурентный паритет, упаковка, мобильная стратегия. Используется как **развёрнутый каталог** требований полного объёма (см. раздел B этого документа). Разд. 36 — обязательные ограничения для доработки.
- `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` — фазированный план реализации (Phase 0..10).
- `backend/app/core/product_spec.py` — программный путь к vNext-spec и краткие правила разд. 36 (`ARCHITECTURE_RULES`, `ENGINEERING_RULES`, `PRODUCT_UX_RULES`, `SIX_QUESTIONS`).

### 0.2 Алгоритм для агента «продолжай по ТЗ»

```text
1. Прочитать README.md → ссылки на ТЗ.
2. Прочитать docs/spec/TZ_FULL_UNIFIED.md (этот файл) — раздел A (MVP) и B (полный объём).
3. Прочитать AI_IMPLEMENTATION_REPORT.md — что было в прошлой волне и какой "Следующий точный шаг".
4. Свериться с docs/audit/TZ_COVERAGE_MATRIX.md (для MVP-задач) или
   docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md (для vNext-фазы).
5. Выбрать минимально достаточное изменение:
   • если есть открытый MVP-пункт со статусом partial/missing → его в первую очередь;
   • иначе — следующий пункт текущей фазы плана (Phase N).
6. Соблюдать §E этого документа (разд. 36 vNext): не ломать существующее,
   feature flags, additive миграции, tenant isolation, типизация, тесты.
7. Закрыть итерацию: обновить AI_IMPLEMENTATION_REPORT.md (handoff),
   при необходимости — TZ_COVERAGE_MATRIX.md и CHANGELOG.md.
```

### 0.3 Конфликты и приоритет

- Если **код противоречит документации** — не правьте код «под» доку молча: зафиксируйте расхождение в `AI_IMPLEMENTATION_REPORT.md`, выберите решение, сохраняющее работающий функционал, и приближающееся к `TZ_FULL_UNIFIED.md`.
- Если **TZ_FULL_UNIFIED противоречит vNext-spec** — побеждает TZ_FULL_UNIFIED (он же синхронизируется с реальным состоянием репозитория), а в vNext остаётся продуктовая рамка/дорожная карта.
- **NEXT_FEATURES.md / TZ.md / spec_compliance_report.md** — историко-справочные; для приёмки не использовать.

---

## A. Объём и приёмка MVP (текущий релизный контур)

> Раздел задаёт **зачётный минимум** платформы. Все требования помечены тегами: `[MVP]` (P0/P1 для релиза), `[v1.1]` / `[v1.2]` / `[v2.0]` (последующие итерации). Машинно-проверяемая матрица — `docs/audit/TZ_COVERAGE_MATRIX.md`.

### A.0 Обязательные артефакты в репозитории

#### A.0.1 ТЗ в репо `[MVP]`
- `docs/spec/TZ_FULL_UNIFIED.md` (этот файл) — единое полное ТЗ с разделами A (MVP) и B (полный объём), оглавлением и якорями.
- Каждое требование помечено тегом `[MVP] / [v1.1] / [v1.2] / [v2.0]`.

#### A.0.2 Матрица покрытия `[MVP]`
- `docs/audit/TZ_COVERAGE_MATRIX.md` со столбцами: `REQ-ID | requirement | backend | db | jobs | events | frontend | tests | status | priority | plan`.
- Статус-словарь (machine-checkable): `done | partial | missing`.

#### A.0.3 README `[MVP]`
- «Quick start (Codespaces / dockerless)» — минимальный путь запуска.
- Ссылки на `TZ_FULL_UNIFIED.md`, `TZ_COVERAGE_MATRIX.md`, `PLATFORM_VNEXT_UPGRADE_SPEC.md`, `AI_IMPLEMENTATION_REPORT.md`, `RELEASE_READINESS.md`.
- «Как зайти в систему для тестов» через env bootstrap без секретов (`ADMIN_BOOTSTRAP=1`).

#### Приёмка A.0 `[MVP]`
- Этот файл существует и полный.
- Матрица заполнена минимум для MVP и критериев приёмки.
- README содержит рабочий быстрый старт и ссылки на канонические документы.

### A.1 Baseline и fail-first отчёт

#### A.1.1 В чистом окружении выполнить `[MVP]`
- `make cs:reset`
- `cp .env.example .env`
- `make cs:dev`
- `make cs:test`
- backend: `source .venv/bin/activate && pytest --collect-only -q`
- frontend: `npm --prefix frontend test`

#### A.1.2 Зафиксировать `[MVP]`
- `docs/audit/BASELINE_VERIFICATION.md` — что работает / не работает / ошибки / шаги воспроизведения.

#### Приёмка A.1 `[MVP]`
- Документ baseline существует и воспроизводим.

### A.2 P0: критические требования

#### A.2.1 Мультиарендность / X-Tenant `[MVP]`
- любой бизнес-роут без `X-Tenant` → 400 (`tenant_required`);
- schema-per-tenant: middleware выставляет `search_path`;
- tenant scope обязателен в репозиториях/ORM-фильтрах;
- файловая изоляция: S3-prefix `tenant/{tenant_id}/...`;
- Тесты: `tests/test_tenant_header_required.py`, `tests/test_files_tenant_isolation_strict.py`.

#### A.2.2 RBAC + ABAC и роли `[MVP]`
- роли уровня аренды: owner / admin / manager / user / auditor + расширенные (методист, юрист, HR, hse_head, …);
- ABAC-атрибуты: `company_id, site_id, document_id, status, risk_level, project_id, contractor_id`;
- единый policy engine; module-level access (vNext-SEC-01) — фильтр доступа к модулям до проверки ресурса;
- Тесты: deny/allow матрица, cross-module boundary (`tests/test_rbac_module_access.py`).

#### A.2.3 Аудит immutable + field-level diff `[MVP]`
- `audit_log` append-only (запрет UPDATE/DELETE на ORM-уровне + DB-trigger);
- who/when/ip/ua/correlation-id + field diff;
- аудит атомарен с бизнес-операцией.

#### A.2.4 Идемпотентность `[MVP]`
- `idempotency_keys{tenant_id, key, endpoint, request_hash, response_payload, created_at}`;
- повтор:
  - тот же hash → тот же результат (replay 202);
  - другой hash → 409.
- KPI-тест: повтор `POST /documents:generate` с тем же ключом возвращает тот же `document_version_id`.

#### A.2.5 Templates strict `[MVP]`
- выбор строго по `(code, version)`;
- уникальность `(code, version)`;
- delete in-use → 409.

#### A.2.6 Outbox + dispatcher `[MVP]`
- `outbox_events{status, attempts, next_retry_at, event_id, dedup}`;
- dispatcher worker: retries / backoff / dead-letter (`OutboxStatus.DEAD`);
- webhook routing: глобальные + per-tenant subscriptions;
- Prometheus metrics (queue depth, dead, attempts).

#### A.2.7 Обязательные доменные события `[MVP]`
- эмит:
  - `DocumentGenerated`
  - `DocumentSigned`
  - `DocumentExported`
  - `RiskAssessed`
  - `PPEIssued`
  - `TrainingCompleted`
- Тесты на ≥3 событий: запись в outbox + dispatch.

#### A.2.8 Pipeline шаги `[MVP]`
- этапы как отдельные шаги со статусом / логом / ретраями;
- модель `DocumentJob` + `DocumentJobStep`;
- маршрут: template → headers → replace → pdf → zip → (sign/edo) → archive;
- timings, attempts, error_code/error_payload.

#### A.2.9 Replace engine `[MVP]`
- dry-run report (CSV/JSON);
- diff preview (структура для UI);
- apply меняет body/tables/hdr/ftr; shapes/textboxes допускаются `[v1.1]`, но явно;
- backup + rollback обязателен.

#### A.2.10 PDF + встроенные шрифты `[MVP]` / `[v1.1]`
- LO headless pool для prod; dev fallback — feature flag (`PDF_FALLBACK=always|never`);
- встройка шрифтов (DejaVu/Noto Sans);
- если не готово в окружении — явный TODO `[v1.1]` в матрице + skip-тест с причиной.

### A.3 P1: MVP домены и пакеты

#### A.3.1 Риски `[MVP]`
- метод PxS + hazards/measures (Fine-Kinney — `[v1.1]`);
- risk map сотрудника / места / объекта;
- план мер + контроль сроков;
- deterministic output;
- событие `RiskAssessed` → outbox.

#### A.3.2 СИЗ + склад `[MVP]` / `[v1.1]`
- нормы СИЗ + карточки + журнал выдачи/возврата `[MVP]`;
- `PPEIssued` / `PPEReturned` → outbox `[MVP]`;
- склад (остатки/партии/сертификаты/инвентаризация) — skeleton `[v1.1]`.

#### A.3.3 Обучение / инструктажи `[MVP]`
- реестр программ / курсов / групп;
- тесты / протоколы / удостоверения через documents pipeline;
- электронные журналы инструктажей (минимум);
- `TrainingCompleted` → outbox.

#### A.3.4 Инциденты / проверки / предписания `[MVP]` / `[v1.2]`
- инциденты: регистрация + расследование + CAPA + сроки `[MVP]`;
- проверки: план / чек-листы минимум `[MVP]`;
- предписания (prescriptions): skeleton `[v1.2]`;
- пакет «подготовка к проверке» (skeleton) `[MVP]`.

#### A.3.5 Пакеты документов `[MVP]`
- «Выход на объект» / «Несчастный случай» / «Подготовка к проверке» / «Обучение»;
- Тесты: 1–2 интеграционных сценария + фикстуры.

### A.4 Frontend: F1..F4

#### A.4.1 Структура feature-based `[MVP]`
- `src/features` (documents, risk, ppe, training, incidents, admin, client-cabinet, …);
- shared слой (`src/shared`/`src/api`/`src/hooks`/`src/permissions`);
- слои entities / widgets / pages / app.

#### A.4.2 Обязательные экраны MVP `[MVP]`
- Login + Tenant selection;
- Dashboard KPI (роле-специфичные workspaces — Phase 1.1, vNext-IA-01);
- Documents: templates list, generation wizard, job timeline, replace dry-run/diff/apply/rollback;
- Risks, PPE, Training, Incidents, Admin, Client cabinet v1.

Полная инвентаризация — `docs/FRONTEND_SCREENS_INVENTORY.md` (82+ экранов).

#### A.4.3 UX-компоненты `[MVP]`
- diff viewer;
- job timeline;
- поиск/фильтры;
- RBAC guard (`<Can />`) для действий/маршрутов;
- bulk actions (минимум).

#### A.4.4 Front tests `[MVP]`
- vitest smoke: app renders, tenant guard flows, key routes render without crash;
- e2e smoke (`frontend/e2e/smoke.spec.ts`, `key-scenarios.spec.ts`).

### A.5 DevX и test discovery

#### A.5.1 Каноничные команды `[MVP]`
- `make cs:reset`, `make cs:dev`, `make cs:test`, `make dev-lite`.

#### A.5.2 Dev-вход без секретов `[MVP]`
- bootstrap admin через env: `ADMIN_BOOTSTRAP=1`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_TENANT`.

#### A.5.3 Test discovery `[MVP]`
- VS Code видит pytest (`.vscode/settings.json`, `scripts/pytest.sh`).

### A.6 Репозиторный hygiene

#### A.6.1 Целевой порядок `[MVP]`
- единый путь установки/запуска;
- единый `.env.example` + docs;
- объединённый «правдивый» runbook;
- удаление мусора только после usage-check и зелёных тестов.

#### A.6.2 Что обязательно описать `[MVP]`
- `docs/repo-structure.md` (легаси) + `docs/PROJECT_STRUCTURE.md` (актуальный);
- `docs/troubleshooting.md`.

#### A.6.3 CI / линтеры `[MVP]` / `[v1.1]`
- ruff/black/mypy, eslint/tsc не ломают разработку `[MVP]`;
- coverage gate `core/domain/services` ≥ 85% — `[v1.1]` (текущий — план подъёма зафиксирован).

### A.7 Критерии приёмки MVP

В чистом Codespace/dockerless окружении:

1. `make cs:reset` `[MVP]`
2. `cp .env.example .env` + `ADMIN_BOOTSTRAP=1` `[MVP]`
3. `make cs:dev` (backend+frontend) `[MVP]`
4. В UI:
   - `documents:generate` (idempotency replay/conflict),
   - replace dry-run/apply/rollback,
   - risk assessment (deterministic + outbox),
   - PPE issue (`PPEIssued`),
   - training completion (`TrainingCompleted`).
5. `make cs:test` зелёный `[MVP]` (~1086 backend + 35+ frontend; цели 1200+ — отслеживается в `AI_IMPLEMENTATION_REPORT`).
6. Тесты видны в VS Code Testing panel `[MVP]`.
7. Документация: `docs/spec` + `docs/audit` + `README.md` ссылки `[MVP]`.

### A.8 Backend B1..B5 / Frontend F1..F4 (фиксация)

| Код | Требование | Тег |
|-----|------------|-----|
| **B1** | tenant isolation + scoped access | `[MVP]` |
| **B2** | RBAC/ABAC policy enforcement (включая module-level) | `[MVP]` |
| **B3** | document pipeline step orchestration | `[MVP]` |
| **B4** | idempotency keys + replay/conflict semantics | `[MVP]` |
| **B5** | outbox/webhooks delivery guarantees + DLQ | `[MVP]` |
| **F1** | feature-based frontend structure | `[MVP]` |
| **F2** | обязательные MVP экраны | `[MVP]` |
| **F3** | UX components (diff/timeline/filter/guards) | `[MVP]` |
| **F4** | frontend smoke tests | `[MVP]` |

---

## B. Полный объём (vNext «эталонная платформа»)

> Раздел B описывает **полный объём**, который превращает MVP в эталонный SaaS-/Enterprise-продукт по ОТ/ПБ/ПромБез/Экологии/обучению/ЭДО. Каждый блок содержит **обязательные элементы** (что должно быть в финале) и ссылку на исчерпывающее описание в `PLATFORM_VNEXT_UPGRADE_SPEC.md`. Не дублируйте формулировки оттуда — используйте этот раздел как карту входа.

> Тег `[full]` означает «требуется для эталонной платформы», но не блокирует MVP. Подчинённые `[v1.1]`/`[v1.2]`/`[v2.0]` указывают целевую фазу.

### B.1 Конкурентный паритет и продуктовая рамка `[full]`
- Паритет с KOT, 1С:EHS, Courson, OTOR, UMS Jums, RiskProf, Sentry EHS — `vNext §1.1`.
- Сильнее конкурентов в 5 направлениях (UX, скорость освоения, расширяемость, надёжность, mobile/field) — `vNext §1.2`.
- Принципы продукта: task-first, role-based workspace, progressive disclosure, zero-duplicate-entry, safe-by-default, mobile as real work surface, self-healing, modular growth, sellability — `vNext §2`.

### B.2 Издания и упаковка `[full]`
- Редакции: Start OT / Business OT / Safety Suite / Enterprise Holding / Training Center Edition / Outsource OT Edition / Contractor Portal Pack / Field & Terminal Pack / AI Copilot Pack / Industrial Extensions Pack — `vNext §3`.
- Биллинг по активным сотрудникам и фактическому использованию; trial/demo/sandbox; ROI-калькулятор; white-label; reseller-кабинет.

### B.3 Информационная архитектура и UI `[full]` / `[v1.1]`
- Двойная навигация (модульная + сценарная) — `vNext §4.1`.
- Role-based workspaces для 16+ ролей: KPI / просрочки / задачи на сегодня / быстрые действия / рекомендации / последние события / календарь / черновики / статус интеграций — `vNext §4.2` (Phase 1.1 — Backend done; полный набор ролей — `[v1.1]`).
- Command Center / центр внимания — `vNext §4.3` (backend готов, frontend `[v1.1]`).
- Smart calendar (day/week/month/year + saved filters + plan/fact + load + SLA + ICS/Outlook/Google export) — `vNext §4.4`.
- Universal search + command bar (CMD+K) с recent items, saved searches, быстрыми командами — `vNext §4.5`.
- Universal card layout (summary, статусы, badges, tabs, timeline, связанные сущности, файлы, задачи, аудит, быстрые действия) — `vNext §4.6`.
- Реестры (фильтры/пагинация/сортировка/массовые действия/saved views/настраиваемые колонки/экспорт/deep links) — `vNext §4.7`.
- Безопасный UX (autosave, drafts, dry-run, preview, rollback, мастера, контекстная помощь, video help) — `vNext §4.8`.

### B.4 Платформенное ядро и master data `[full]` / `[v1.1]`
- Базовые сущности (`vNext §5.1`): группы компаний, компании, филиалы, объекты, площадки, подразделения, рабочие места, должности, профессии, сотрудники, назначения, подрядчики, посетители, оборудование, договоры, проекты.
- Единая карточка сотрудника (360°) — `vNext §5.2`. Phase 3.2 backend, frontend deferred.
- Единая карточка объекта — `vNext §5.3`.
- Data Quality Layer + Data Quality Dashboard — `vNext §5.4`. Backend MVP сделан (Phase 3.1, 10 правил движка), Dashboard UI `[v1.1]`.

### B.5 Документная фабрика и ЭДО-контур `[full]`
- Сквозная трассировка: template → version → layout → replace map → pipeline profile → instance → version → approvals → signatures → archive → external delivery (`vNext §6.1`).
- Template Engine (placeholders, conditions, loops, nested tables, calculated, склонения, fallback, brand templates, variable inspector, test render) — `vNext §6.2`.
- Header/Footer Engine (first/even/odd, PAGE/NUMPAGES, QR, watermark, штампы, реквизиты, ГОСТ-профили, document passport) — `vNext §6.3`.
- Replace Engine (body/tables/hdr/ftr/textboxes, regex/whole-word, dry-run/diff/rollback, CSV maps, dictionaries, нормализация runs) — `vNext §6.4`.
- Pipeline Engine (Generate→HF→Replace→PDF→Approval→Sign→Archive→EDO/Portal, restart from failed, idempotent rerun, parallelism, SLA, downloadable execution report) — `vNext §6.5`.
- PDF: устойчивый LO pool, retry, контроль зависаний, кириллица + встроенные шрифты, post-conversion validation — `vNext §6.6`.
- Document readiness score — `vNext §6.7`.
- Compare / visual diff (версия-к-версии, diff содержимого / набора / правил / зависимостей от НПА / печатных форм) — `vNext §6.8`.
- ЭДО и подпись (КЭП/УНЭП/МЧД/ПЭП, mobile sign, исходящие/входящие, статусы оператора, роуминг, квитанции) — `vNext §6.9`.
- Реестр локальных актов и НПА (federal/local НПА, инструкции, программы, положения, приказы, акты, журналы, статус актуальности, история ознакомлений) — `vNext §6.10`.

### B.6 LMS и проверки знаний `[full]` / `[v1.1]`
- Ядро обучения, кабинет предприятия и кабинет слушателя, внутреннее обучение на большой штат, LMS-ready (контент / SCORM-ready / question bank / adaptive / proctoring / mobile learning) — `vNext §7.1–7.4`.
- Внешние интеграции: ФРДО / ЕИСОТ / Госключ / внешние LMS / HR-системы — `vNext §7.5` `[v1.1]`.

### B.7 Инструктажи, журналы, знания `[full]` / `[v1.1]`
- Все типы инструктажей, электронные журналы, версионирование инструкций — `vNext §8.1–8.2`.
- База знаний (knowledge hub) — `vNext §8.3`.
- Терминальный/kiosk-сценарий с биометрией/QR/NFC, screen signature, фото-/видеофиксация, offline edge mode — `vNext §8.4` (`[v1.1]`).

### B.8 Медосмотры, психиатрия, здоровье `[full]`
- Контингент / поименные списки / периодические / предварительные / психиатрические / флюорография / санкнижки / противопоказания / договоры с медорганизациями / направления / результаты / контроль сроков / бюджет / отстранение — `vNext §9.1`.
- Автоматизация: формирование контингента, влияние СОУТ/рисков, события календаря, блокировка допуска при противопоказании — `vNext §9.2`.
- Health-контур: предсменные / транспортные осмотры / медоборудование — `vNext §9.3` `[v1.2]`.

### B.9 СОУТ `[full]`
- Карты СОУТ / классы условий труда / вредные факторы / компенсации / сроки замеров / производственный контроль / связи с СИЗ/медосмотрами/рисками — `vNext §10.1`.
- Автоматизация: импорт результатов, связи с рабочими местами, пересчёт смежных обязательств — `vNext §10.2`.

### B.10 Risk engine и меры управления `[full]`
- Полноценный risk engine не ниже RiskProf: matrix / Fine-Kinney / tenant-specific методики / гибкие шкалы / коэффициенты / risk register / hazard register / control measures / residual risk / CAPA / reports / maps — `vNext §11.1`.
- Централизованная база опасностей и мер с привязкой к НПА — `vNext §11.2`.
- Автоматизированное формирование (загрузка штатки, импорт оргструктуры, интеграция с СОУТ, автогенерация инструкций/мероприятий/перечней СИЗ/медосмотров) — `vNext §11.3`.
- Редактируемость и версионируемость результата — `vNext §11.4`.
- Связь с инцидентами/проверками — `vNext §11.5`.

### B.11 СИЗ, нормы, склад, бюджет `[full]` / `[v1.1]`
- Нормирование (типовые/по профессии/по вредности/сезонность/альтернативы/антропометрия/сертификаты) — `vNext §12.1`.
- Личные карточки СИЗ (положенные/выданные/размеры/сроки/замены/возврат/списание/timeline) — `vNext §12.2`.
- Склад: номенклатура, партии, остатки, перемещения, резервирование, инвентаризация, поставщики, прогноз дефицита — `vNext §12.3` `[v1.1]`.
- Бюджет безопасности (СИЗ / обучение / медосмотры / мероприятия / план vs факт / аналитика) — `vNext §12.4` `[v1.1]`.
- Мобильная выдача с QR / штрихкодом / фото / подписью / offline — `vNext §12.5` `[v1.1]`.

### B.12 Инциденты, микротравмы, НС, профзаболевания `[full]`
- Микротравмы / НС / инциденты без пострадавших / подрядчики / посетители / профзаболевания / near-miss / severity / фото-видео / planы / ущерб / дедлайны — `vNext §13.1`.
- Расследование (комиссии / акты / приказы / пакеты / CAPA / связь с рисками и НПА) — `vNext §13.2`.
- Аналитика инцидентов (root cause, тренды, severity matrix, cost) — `vNext §13.3`.

### B.13 Проверки, аудиты, наблюдения, CAPA `[full]` / `[v1.1]`
- Все типы проверок (плановые/внеплановые/внутренние/внешние/тематические/гос/мобильные) с чек-листами, фото/видео, голосом, геометкой, offline mode — `vNext §14.1`.
- Поведенческие аудиты (BBS) — `vNext §14.2` `[v1.1]`.
- Предписания и CAPA (исполнители, дедлайны, доказательства, повторные проверки, эскалации, % закрытия, связь с рисками/инцидентами/НПА) — `vNext §14.3`.

### B.14 Подрядчики, посетители, допуск `[full]`
- Contractor management (карточки, договоры, объекты, сотрудники, документы, проверки готовности, дедлайны, внешний кабинет) — `vNext §15.1`.
- Guided data collection (пошаговый сбор данных подрядчика) — `vNext §15.2`.
- Visitors / guests (регистрация, инструктаж, временный доступ, журнал) — `vNext §15.3`.
- Readiness engine допуска: что готово / просрочено / отсутствует / почему нельзя — `vNext §15.4`.

### B.15 Наряды-допуски и работы повышенной опасности `[full]` / `[v1.2]`
- Шаблоны нарядов / виды работ / зоны / оборудование / бригада / условия допуска / mobile open/close / фотофиксация / блокировка по просроченным допускам — `vNext §16`.

### B.16 Equipment / Asset / Транспорт / ОПО / Электробезопасность `[full]` / `[v1.2]`
- Asset registry — `vNext §17.1`.
- ОПО / ТУ / ЗиС — `vNext §17.2`.
- Transport safety — `vNext §17.3`.
- Электробезопасность (группы допуска / средства защиты / журналы) — `vNext §17.4`.

### B.17 Комитеты, комиссии, заседания `[full]` / `[v1.1]`
- Комитеты ОТ/ПБ, комиссии по обучению/расследованиям, повестки, приглашения, протоколы, решения, голосование, задачи, KPI исполнения — `vNext §18`.

### B.18 НПА и compliance management `[full]`
- Реестр НПА (federal/local, редакции, даты, owner, статус актуальности) — `vNext §19.1`.
- Obligation register (привязка требования к роли/объекту/процессу, доказательства, периодичность, severity) — `vNext §19.2`.
- Impact analysis (какие шаблоны / документы / инструкции / риски / задачи зависят от НПА) — `vNext §19.3`.
- Обновление нормативного контента (draft → publish → diff → notify → tasks) — `vNext §19.4`.

### B.19 Вертикальные контуры (ПБ / ПромБез / Экология / ГО-ЧС) `[full]` / `[v1.2]`
- Пожарная безопасность — `vNext §20.1`.
- Промышленная безопасность — `vNext §20.2`.
- Экология (источники загрязнений, выбросы, отходы, НВОС, отчётность) — `vNext §20.3`.
- ГО / ЧС — `vNext §20.4`.

### B.20 Терминалы, kiosk-mode, биометрия, СКУД `[full]` / `[v2.0]`
- Полный enterprise/industrial pack — `vNext §21`.

### B.21 Видеоналитика и computer vision (опциональный pack) `[full]` / `[v2.0]`
- Контроль СИЗ / опасных зон / периметра / автогенерация инцидентов — `vNext §22`.

### B.22 CRM, клиентский кабинет, sellability `[full]` / `[v1.1]`
- CRM-контур (lead → deal → contract → invoice → act → ЭДО → оплата → продление) — `vNext §23.1`.
- Клиентский кабинет (компании / объекты / статусы / недостающие данные / readiness / задачи) — `vNext §23.2`.
- Trial / demo / sandbox / guided demo / self-service trial — `vNext §23.3`.
- White-label / partner / multi-client (для аутсорсеров) — `vNext §23.4`.

### B.23 Аналитика, отчёты, report builder `[full]` / `[v1.1]`
- Операционные дашборды по всем доменам — `vNext §24.1`.
- Управленческие дашборды (по группе / филиалам / объектам / подрядчикам / бюджету / SLA) — `vNext §24.2`.
- Report builder (готовые шаблоны / кастомные отчёты / scheduled delivery / экспорт PDF/XLSX/CSV / tenant-safe sharing) — `vNext §24.3`.
- Product analytics (TTFV / abandoned wizards / часто ошибающиеся формы / самые используемые функции) — `vNext §24.4`.

### B.24 Workflow / Rules / Smart Recommendations `[full]` / `[v1.2]`
- Workflow engine (визуальный редактор / human tasks / approvals / timers / conditions / webhooks / versioning / migration) — `vNext §25.1`.
- Rules engine (условия / действия / приоритеты / dry-run / тестирование правил / лог срабатываний / tenant overrides) — `vNext §25.2`.
- Smart recommendations — `vNext §25.3`.

### B.25 AI Copilot (вспомогательный, не автономный) `[full]` / `[v2.0]`
- Поиск по базе знаний и НПА / explanation «почему не готов» / draft summary расследования / draft CAPA / draft писем / draft инструкций / semantic search — `vNext §26`.
- AI не подписывает / не утверждает / не меняет нормативную логику без подтверждения пользователя.

### B.26 Мобильная стратегия `[full]` / `[v1.1]`
- Двухконтурная модель (PWA + field-app/kiosk) — `vNext §27.1`.
- Mobile-first сценарии (approve/sign / инструктаж / мини-тест / инцидент / чек-лист / фото-видео / голос / выдача СИЗ / поиск сотрудника / проверка допуска) — `vNext §27.2`.
- Offline (задания / чек-листы / карточки / фото-видео / черновики / очередь действий / сканирование / kiosk) — `vNext §27.3`.
- Sync + conflict resolution UI — `vNext §27.4`.

### B.27 Backend-архитектура `[full]`
- Стек: Python 3.12 / FastAPI / Pydantic v2 / SQLAlchemy 2 / PostgreSQL / Alembic / Celery / Redis / MinIO/S3 / LO headless / ClamAV / OpenTelemetry / Prometheus/Grafana / Docker / Traefik — `vNext §28.1`.
- Стиль: модульный монолит, события между модулями, отдельные worker-контуры, plugin-ready, четкое разделение API / application / domain / infrastructure — `vNext §28.2`.
- Bounded contexts (минимальный набор) — `vNext §28.3`.
- Расширяемость: единый event catalog / модульные контракты / plugin registry / public extension points / UI plugin zones / low-code forms / feature flags / canary rollout — `vNext §28.4`.

### B.28 Frontend-архитектура `[full]`
- Стек: React 18+ / TS strict / Vite / React Router / Zustand или RTK / TanStack Query / RHF / Zod / design system / enterprise data grid / PWA — `vNext §29.1`.
- Продуктовые паттерны (workspaces, task inbox, attention center, command bar, drafts, timeline, compare, bulk, smart filters, saved views, contextual help) — `vNext §29.2`.
- UX-требования к сложным экранам (что это / в каком статусе / что сломано / что делать дальше / кто ответственный / что связано / что изменилось) — `vNext §29.3`.

### B.29 API, интеграции, импорт `[full]`
- REST v1 / OpenAPI / Idempotency-Key / pagination/filtering/sorting / webhooks / API keys & OAuth — `vNext §30.1`.
- Интеграции: 1С:ЗУП/ERP / HR / CRM / LMS / ЭДО / ФРДО / ЕИСОТ / почта / Telegram / SMS / SSO/OIDC/SAML/LDAP / СКУД / BI/DWH / CCTV / медорганизации / calendaring / external storage — `vNext §30.2`.
- Импорт и миграция (Excel/CSV / 1С / legacy / mapping UI / validation / preview / migration scripts / partial success) — `vNext §30.3`.

### B.30 Надёжность и эксплуатационная зрелость `[full]`
- Reliability layer: idempotency / outbox / inbox dedup / retries / exp backoff / DLQ / poison queues / distributed locks / circuit breakers / job heartbeat / stuck-job watchdog / temp-file cleanup / storage integrity check — `vNext §31.1`.
- Очереди: documents / PDF / imports / exports / notifications / integrations / search indexing / mobile sync / AI — `vNext §31.2`.
- Self-healing — `vNext §31.3`.
- Производительность (API p95 ≤ 1 с, search p95 ≤ 1.5 с, batch 30 DOCX→PDF p95 ≤ 60 с, replace 500 файлов ≤ 3 мин, 1000 одновременных пользователей в аренде) — `vNext §31.4`.
- Observability (JSON logs / correlation-id / tenant_id / trace API→worker→integration / metrics / dashboards / alerting) — `vNext §31.5`.
- Backup / DR (PostgreSQL daily backup / S3 versioning / RTO ≤ 4ч / RPO ≤ 24ч / restore drills) — `vNext §31.6`.

### B.31 Безопасность и соответствие `[full]`
- JWT access/refresh / SSO-ready / tenant isolation / RBAC + ABAC / signed URLs / PII masking / encryption / immutable audit / admin action log / safe file handling / antivirus / macro restrictions / session management / forced logout / access trace / retention / export & deletion для ПДн / ФЗ-152 — `vNext §32`.

### B.32 Onboarding клиента `[full]` / `[v1.1]`
- Tenant onboarding wizard — `vNext §33.1`.
- Startup checklist — `vNext §33.2`.
- In-app help / video / support chat / diagnostic panel — `vNext §33.3`.

### B.33 Sellability и trust `[full]`
- Demo tenant / интерактивные сценарии / quick-start / ROI / case library / trust center / страница безопасности / статусы сервиса / API docs / прозрачные тарифы / self-service trial / брендируемый портал — `vNext §34`.

### B.34 Критерии приёмки vNext (см. раздел F)

См. ниже раздел F (vNext §35).

---

## B-NEXT. Расширение объёма: аутсорсинг, модульность, UX, безопасность, эксплуатация

(бизнес-, security- и ops-дополнения №1–№4, разделы 49–74)

> Требования этого раздела уточняют бизнес-модель, безопасность и эксплуатацию.
> Полный текст — в Дополнениях №1–№4 к ТЗ (`docs/spec/appendix/`); здесь — карта.
> Теги: **[vNext-BIZ]** (Доп.1–2, разд. 49–62), **[vNext-SEC]** (Доп.3, разд. 63–70),
> **[vNext-OPS]** (Доп.4, разд. 71–74). Приоритет волн — в
> `PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` (фазы 11–20); REQ-ID — в
> `TZ_COVERAGE_MATRIX.md` (`BIZ-*`, `SEC-*`, `OPS-*`). Программные константы —
> `backend/app/core/product_spec.py` (`BIZ_DOMAINS`, `UX_BUDGET`, `SECURITY_DOMAINS`,
> `LIFECYCLE_DOMAINS` и др.).

### B-NEXT.1 Аутсорсинговый контур [vNext-BIZ]
- Managed Clients + единое окно аутсорсера (Client Cockpit) — разд. 49.
- Сценарные разовые комплекты (Quick Pack Wizard) — разд. 50.
- Client Change Feed + Compliance Baseline — разд. 51.

### B-NEXT.2 Тиражирование: продажа и аренда [vNext-BIZ]
- Иерархия Platform Owner → Reseller → Client, white-label,
  тиражирование настроек (starter-packs) — разд. 52.
- Self-service аренда, редакции, бесшовные переходы — разд. 53.

### B-NEXT.3 Мультидисциплинарность [vNext-BIZ]
- ПБ, ПромБез, Экология, ГО-ЧС, БДД как надстройки над общим ядром —
  разд. 54–57.

### B-NEXT.4 Простота интерфейса (UX-бюджет) [vNext-BIZ]
- Измеримый UX-бюджет экрана + «одна задача — один экран» — разд. 59.
- Чек-лист приёмки экрана (UX Definition of Done) — разд. 60.

### B-NEXT.5 Модульная поставка (entitlements) [vNext-BIZ]
- Module Registry + per-tenant entitlements (default-OFF),
  сквозной enforcement на 3 слоях — разд. 61.

### B-NEXT.6 Приёмка бизнес-расширения
- Критерии приёмки бизнес-дополнений — Доп.№1 разд. 58, Доп.№2 разд. 60/61.

### B-NEXT.7 Сквозная безопасность [vNext-SEC]
- Модель угроз новых поверхностей (иерархия, impersonation,
  entitlements) — разд. 63.
- AppSec: OWASP, безопасный парсинг документов (**XXE-fix закрыт**,
  `backend/app/core/xml_security.py`), SSRF-защита — разд. 64.
- RLS как второй рубеж изоляции — разд. 65.
- ПДн/152-ФЗ (локализация, права субъекта, DPA) — разд. 66.
- Единая политика секретов (шифрование, ротация) — разд. 67.
- Внешний контур: magic links, anti-abuse — разд. 68.
- Security в CI (SAST/DAST) + пентест — разд. 69.

### B-NEXT.8 Данные, ЖЦ клиента, API, эксплуатация [vNext-OPS]
- Импорт-фреймворк + миграция с источников (Excel/1С/конкуренты) —
  разд. 71.
- Жизненный цикл клиента: онбординг → офбординг, экспорт/удаление
  данных, retention — разд. 72.
- Версионирование API + deprecation policy — разд. 73.
- Zero-downtime деплой, expand-contract миграции, откат — разд. 74.

---

## C. Текущее состояние реализации (как зафиксировано)

> Этот раздел — **указатель на живые источники**, а не дублирование статуса. Не править здесь без сверки с актуальными отчётами.

- **Сводка статуса:** `AI_IMPLEMENTATION_REPORT.md` (последний handoff в начале файла + раздел `Current Status`).
- **MVP-матрица (REQ-ID → status):** `docs/audit/TZ_COVERAGE_MATRIX.md`.
- **Готовность к релизу:** `RELEASE_READINESS.md` + `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`.
- **Открытые блокеры:** `GAP_REPORT.md`.
- **Известные ограничения:** `KNOWN_LIMITATIONS.md`.

Краткий снимок (для ориентировки, актуальное состояние — в файлах выше):

- Все P0 (`A.2.1–A.2.10`) — `done`, кроме точек, явно отмеченных в матрице.
- P1 домены (`A.3.1 / A.3.2 / A.3.3 / A.3.4 / A.3.5`) — `done` для MVP-объёма; склад / предписания — `partial` `[v1.1–v1.2]`.
- F1..F4 — `done`; полная инвентаризация экранов есть.
- vNext Phase 0 (Baseline re-verification) — инфраструктура готова, пере-прогон в чистом окружении — `pending` (RB-001, RC-001).
- vNext Phase 1 (Architectural foundation) — `complete` (Workspaces / RBAC module / Tenant isolation audit).
- vNext Phase 2 (Operational dashboard / Health checks) — backend `done`, frontend `pending`.
- vNext Phase 3 (Data Quality + Unified Employee Card) — DQ backend MVP `done` (10 правил движка), DQ Dashboard frontend и Employee Card aggregate — `pending`.
- vNext Phases 4–10 — `planned` (см. §D).
- vNext Phase 3 (Data Quality + Unified Employee Card) — DQ backend MVP `done` (10 правил), DQ Dashboard frontend `done`, Employee Card backend aggregate + UI + Documents/Briefings/Deadlines секции `done` (Sessions 19/20/21 — `GET /api/v1/employees/{id}` + `EmployeeCardPage.tsx` 11 табов).
- vNext Phase 4 (Calendar & Search) — `done`. Smart Calendar backend aggregator (Session 22) + UI (Session 23 — `CalendarPage.tsx` с day/week/month/year/list, фильтры по source_types/person_id/site_id, drill-down, overdue highlighting, split-permission `CALENDAR_VIEW`); ICS export (Session 24 — `/calendar/events.ics`); plan/fact comparison (Sessions 25–26); SLA tracking backend + UI (Sessions 27–28); resource load heatmap, saved views CRUD, CMD+K palette с entity grouping (Sessions 29–32); backend `SearchService.search()` accuracy tests (`tests/test_search_service_accuracy.py`, 8 кейсов); saved-search shortcuts и recent clicked entities в CMD+K palette (`CommandBar.tsx` секции «Сохранённые запросы» + «Недавно открытые» с persistent `ux.commandbar.recentEntities.v1` + ↑↓/Enter keyboard nav).
- vNext Phase 4 (Calendar & Search) — **COMPLETE.** Smart Calendar Task 4.1 `done` (Sessions 22-30 — backend aggregator + UI day/week/month/year/list + ICS export RFC 5545 + plan/fact comparison + SLA tracking + resource load heatmap + saved per-user views); Universal Search Task 4.2 `done` (Sessions 31-35 — pre-existing backend FTS index + CMD+K palette с entity results grouped by 24 types + 7 type-to-execute commands + ARIA listbox keyboard nav ↑↓/Enter/Home/End + saved searches в палитре с lazy session-cache (S34) + client-side recent-entities tracking с 30-day TTL + dedup (S35) + backend `SearchService` index accuracy tests 35 cases / 6 classes (S33)). Optional polish (non-acceptance): score-based unified ranking, per-tenant relevance tuning, i18n executable commands.
- vNext Phases 5–10 — `planned` (см. §D).

---

## D. Дорожная карта реализации (фазы)

> Полное содержание — `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`. Здесь — короткая навигация. Не плодить альтернативные roadmap-файлы.

| Фаза | Приоритет | Фокус | Status |
|------|-----------|-------|--------|
| Phase 0 — Release Blockers | P0 | TZ-1.1 baseline re-verification, RC-001..006 | 🔴 deferred |
| Phase 1 — Architectural Foundation | P1 | Role-based workspaces / RBAC module / Tenant isolation audit | ✅ complete |
| Phase 2 — Operational Dashboard | P1 | Command Center / Health Check Engine | 🟡 backend done, frontend pending |
| Phase 3 — Data Quality & Master Data | P1 | DQ Layer / Unified Employee Card / Site Card | 🟢 DQ + Employee Card (backend + UI + Documents/Briefings/Deadlines) done; Site Card pending |
| Phase 4 — Calendar & Search | P2 | Smart Calendar / Universal Search / Command Bar | ✅ complete (Sessions 22–32 + Phase 4.2 tail: SearchService accuracy tests + saved-search shortcuts + recent clicked entities in CMD+K palette) |
| Phase 5 — Document Factory Hardening | P2 | Template lint / Compare / Header-footer / Replace edge cases | 🟡 Phase 5.1 — template lint extended (else/elif + unbalanced delim + available_fields), Variable Inspector (`GET /templates/{tid}/versions/{vid}/variables` + `inspect_template_variables()`), render edge-case suite (42 cases — null/0/False/empty/Cyrillic/XML-chars/filters/if-elif-else/loops/header.xml/sandbox) done; preview accuracy and migration of existing templates pending; Task 5.2 (Header/Footer + Replace) not started |
| Phase 6 — Integration & Webhooks | P2 | Webhook delivery / Public API hardening / Импорт | 📋 planned |
| Phase 7 — Mobile & Field-Ready | P2 | PWA hardening / Offline sync / Field workflows / Kiosk | 📋 planned |
| Phase 8 — Analytics & Reporting | P3 | Operational + Management dashboards / Report builder / Product analytics | 📋 planned |
| Phase 9 — Performance & Scale | P3 | Query optimization / Partitioning / Caching | 📋 planned |
| Phase 4 — Calendar & Search | P2 | Smart Calendar / Universal Search / Command Bar | ✅ COMPLETE — 4.1 Smart Calendar 100% done (Sessions 22-30); 4.2 Universal Search 100% done (Sessions 31-35, CMD+K palette + keyboard nav + saved-searches + recent-entities + backend test coverage); optional polish (non-acceptance): score-based ranking, per-tenant relevance tuning, i18n executable commands |
| Phase 5 — Document Factory Hardening | P2 | Template lint / Compare / Header-footer / Replace edge cases | ✅ COMPLETE (Sessions 36-40: linter + inspector + audit + preview parity; 50 replace + 33 header/footer tests) |
| Phase 6 — Integration & Webhooks | P2 | Webhook delivery / Public API hardening / Импорт | ✅ COMPLETE (Session 41 — webhook CRUD pin + 28 tests; Session 42 — public API pin + 24 tests) |
| Phase 7 — Mobile & Field-Ready | P2 | PWA hardening / Offline sync / Field workflows / Kiosk | 🟡 7.1 PWA sync pinned Session 43 — 28 tests; 7.2 field UX frontend-only deferred |
| Phase 8 — Analytics & Reporting | P3 | Operational + Management dashboards / Report builder / Product analytics | ✅ COMPLETE (Session 44 — 34 analytics tests; Session 45 — 26 audit-API tests) |
| Phase 9 — Performance & Scale | P3 | Query optimization / Partitioning / Caching | 🟡 9.1 query benchmarks pinned Session 46 (24 cases); 9.2 HTTP cache (ETag) — Sessions 47-49 closed 7/7 main list endpoints (55 tests); S50 shared `compute_list_etag` helper + 17 unit tests; S51 added ppe/items, ppe/issues, prescriptions (16); S52 added briefings/{templates,journals,entries} + training/courses (15); S53 added medical/exams + departments (13) — **16 list endpoints carry ETag, 116 contract tests total**; remaining list endpoints + service-level Redis cache + Cache-Control uniformity audit + slow-query identification + date partitioning remain follow-ups |
| Phase 10 — Enterprise Features | P3 | SSO/SAML / White-label / I18n / CRM / AI Copilot / Verticals (ПБ/ПромБез/Экология/ГО-ЧС/Видеоналитика) | 📋 planned |

**Правило выбора задачи:** если открыт MVP-пункт со статусом `partial`/`missing` — он первичен; иначе — следующий пункт текущей фазы плана; в любом случае — соблюдение §E.

---

## E. Обязательные правила доработки (разд. 36 vNext)

> Полные формулировки и шесть вопросов — `vNext §36` и `backend/app/core/product_spec.py`.

### E.1 Архитектурные ограничения (`ARCHITECTURE_RULES`)

1. Не ломать существующие рабочие модули.
2. Не удалять действующие API без слоя совместимости.
3. Все новые функции — через feature flags.
4. Additive DB migrations; сохранять tenant isolation; не смешивать bounded contexts напрямую; тяжёлые операции — в async workers.

### E.2 Инженерные требования (`ENGINEERING_RULES`)

- Unit / integration / e2e тесты;
- покрытие новых доменных инвариантов;
- документировать новые endpoints (OpenAPI);
- вести `CHANGELOG.md`;
- обновлять OpenAPI;
- seed/demo данные;
- migration scripts;
- correlation-id в логах;
- строгая типизация на backend и frontend.

### E.3 Product / UX (`PRODUCT_UX_RULES`)

- Новый экран — только с определённой primary user goal;
- новая сущность — только с привязкой к existing master data;
- не плодить workflow, если хватает rules / presets / tasks;
- не перегружать формы; progressive disclosure;
- массовые операции — только с preview, прогрессом, rollback;
- mobile / field функции — только с учётом offline.

### E.4 Шесть обязательных вопросов к каждой новой функции (`SIX_QUESTIONS`)

1. Для какой роли она нужна?
2. В каком сценарии она используется?
3. Какие данные ей нужны и откуда они берутся?
4. Как ведёт себя при отсутствии сети / ошибке интеграции?
5. Как пользователь понимает, что произошло и что делать дальше?
6. Как отключается / включается по tenant без глобального refactor?

---

## F. Критерии приёмки по ключевым блокам (vNext §35)

### F.1 UX и сценарии
- новый пользователь своей роли может выполнить базовый сценарий без внешнего обучения;
- в ключевых сценариях нет перегруженных экранов;
- есть safe preview / dry-run для массовых действий;
- workspace отличается по ролям.

### F.2 Документы
- `documents:generate` с одинаковым `Idempotency-Key` возвращает один бизнес-результат;
- PDF корректен (встроенные шрифты, кириллица);
- readiness score объясняет неготовность;
- diff версий работает;
- replace rollback работает.

### F.3 Обучение
- массовые назначения работают на large batch;
- есть кабинет предприятия и кабинет слушателя;
- протоколы и подписи работают;
- уведомления по отстающим / просроченным работают.

### F.4 Медосмотры / СОУТ / Риски
- СОУТ влияет на медосмотры, СИЗ и риски;
- risk engine собирает результат из штатки + СОУТ + настроек;
- результаты редактируемы и версионируемы.

### F.5 СИЗ и склад
- личные карточки корректны;
- есть остатки, партии, закупки, прогнозы;
- выдача с мобильного работает;
- бюджет не конфликтует со складским учётом.

### F.6 Инциденты / проверки
- фото / видео — first-class evidence;
- offline field capture работает;
- CAPA влияет на статусы и аналитику;
- checklist + акт + предписание формируются автоматически.

### F.7 Подрядчики и допуск
- внешний контур простой и пошаговый;
- readiness допуска показывает причины блокировки;
- данные подрядчика валидируются до запуска допуска.

### F.8 Надёжность
- watchdog ловит зависшие jobs;
- retries и DLQ работают;
- outbox / webhook dedup работает;
- после временного сбоя внешней интеграции платформа не теряет данные.

### F.9 Mobile
- approve / reject / sign доступны с мобильного;
- audits / checklists / incidents / СИЗ-issue работают в field mode;
- offline queue и conflict UI работают.

---

## G. Карта канонических документов и запрет на дубли

| Назначение | Канонический файл | Не дублировать в |
|------------|--------------------|-------------------|
| Объём и приёмка (этот файл) | `docs/spec/TZ_FULL_UNIFIED.md` | где угодно |
| Продуктовая рамка vNext, разделы 0–37 | `docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md` | в TZ_FULL — только ссылки |
| Краткие правила разд. 36 vNext (программно) | `backend/app/core/product_spec.py` | не копировать в .md |
| Хаб ТЗ (точка входа) | `docs/spec/README.md` + `docs/spec/TZ_OVERVIEW.md` | не плодить альтернативные «обзоры» |
| Дорожная карта реализации | `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` | не плодить альтернативные roadmaps |
| Матрица покрытия требований | `docs/audit/TZ_COVERAGE_MATRIX.md` | не дублировать в md-таблицах |
| Журнал волн и handoff | `AI_IMPLEMENTATION_REPORT.md` | не делать `*_REPORT_*.md` параллельно |
| Готовность к релизу | `RELEASE_READINESS.md` (+ canonical: `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`) | дублирование запрещено |
| Известные ограничения | `KNOWN_LIMITATIONS.md` | один файл на репо |
| Архитектура | `docs/ARCHITECTURE.md` | согласованно с README и MODULES.md |
| Инвентаризация экранов | `docs/FRONTEND_SCREENS_INVENTORY.md` | один файл |
| Кандидаты на чистку | `docs/CLEANUP_CANDIDATES.md` | один файл |
| Workflow для агентов | `docs/AI_AGENT_WORKFLOW.md` (+ `AGENTS.md`, `.cursor/rules/*.mdc`) | согласованно |

### Документы, помеченные как deprecated (см. §G.1)

| Файл | Что делать |
|------|-----------|
| `docs/NEXT_FEATURES.md` | **Deprecated.** Содержание перенесено в раздел B этого файла и в `PLATFORM_VNEXT_UPGRADE_SPEC.md §7–§30`. Кандидат на удаление в следующей волне (см. `docs/CLEANUP_CANDIDATES.md`). |
| `docs/spec/TZ.md` | Историческая первая версия ТЗ. Хранить только как archive; новых ссылок не плодить. |
| `docs/spec_compliance_report.md` / `docs/p1_compliance_report.md` | Замкнутые отчёты прошлых волн; статус истинный — в `TZ_COVERAGE_MATRIX.md`. |
| `docs/SPEC_TRACEABILITY_MATRIX.md` | Перекрывается `TZ_COVERAGE_MATRIX.md`; держать как навигационный индекс или удалить. |

### G.1 Принципы чистки

1. Любые новые требования — только в `TZ_FULL_UNIFIED.md` (этот файл).
2. Любая дорожная карта — только в `PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`.
3. Любой статус MVP — только в `TZ_COVERAGE_MATRIX.md`.
4. Любой релиз-вердикт — только в `RELEASE_READINESS.md` + `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`.
5. При удалении файла — обновить ссылки в `README.md`, `docs/README.md`, `docs/CLEANUP_CANDIDATES.md`.

---

## H. Финальный отчёт в PR (шаблон)

В PR, закрывающем итерацию «по ТЗ», дать:

- Краткое резюме: сколько требований `[MVP]` `done` / `partial` / `missing` (взять из `TZ_COVERAGE_MATRIX.md`).
- Какие пункты `A.2`/`A.3` или фаза `D.PhaseN` затронуты и что закрыто.
- Список изменённых файлов и почему (в т.ч. backend/frontend/tests/migrations/docs).
- Команды запуска / тестов (как в README; что прогонялось локально, что — только CI).
- Что отложено на `[v1.1]`/`[v1.2]`/`[v2.0]` и почему.
- Связанные обновления `AI_IMPLEMENTATION_REPORT.md` (handoff: «Следующий точный шаг»).
- Связанные обновления `CHANGELOG.md`.

---

## Приложения

### Прил. 1. Карта Backend B1..B5 → код

| Код | Канонические модули |
|-----|---------------------|
| B1 | `backend/app/middleware/tenant.py`, `backend/app/db/tenant_row_guard.py`, `backend/app/modules/tenancy/*` |
| B2 | `backend/app/modules/rbac_abac/{engine,permission_codes,deps}.py` |
| B3 | `backend/app/modules/pipelines/orchestrator.py`, `backend/app/services/pipelines_orchestrator.py` |
| B4 | `backend/app/services/idempotency.py` |
| B5 | `backend/app/services/{outbox,webhooks,events}.py`, `backend/app/modules/operational_dashboard/*` |

### Прил. 2. Карта Frontend F1..F4 → код

| Код | Канонические пути |
|-----|-------------------|
| F1 | `frontend/src/features/*`, `frontend/src/router/{features,pageRegistry,routeGroups}.tsx` |
| F2 | `frontend/src/pages/*`, `frontend/src/router/AppRouter.tsx` |
| F3 | `frontend/src/permissions/*`, `frontend/src/components/*` (Can / DataTable / JobTimeline / ApprovalTimeline / WizardJobTimeline) |
| F4 | `frontend/e2e/{smoke,key-scenarios}.spec.ts`, `frontend/vitest.critical.config.ts` |

### Прил. 3. Источники для тегов `[MVP]/[v1.1]/[v1.2]/[v2.0]`

- `[MVP]` — раздел A этого файла + строки `done`/`partial`/`missing` со `priority=p0/p1` в `TZ_COVERAGE_MATRIX.md`.
- `[v1.1]/[v1.2]/[v2.0]` — раздел B этого файла + Phases 4–10 в `PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`.

### Прил. 4. Bounded contexts → реальные модули backend (vNext §28.3)

| Bounded context (vNext §28.3) | Backend модуль / роут | Статус |
|-------------------------------|----------------------|--------|
| IAM / Tenancy | `backend/app/modules/{tenancy,rbac_abac}/*`, `backend/app/middleware/tenant.py` | MVP done |
| Organizations / HR Core | `backend/app/modules/org_structure/*`, `backend/app/api/routes/{companies,sites,departments,persons,tenancy,tenants}.py` | MVP done |
| Documents | `backend/app/modules/{templates,branding,headers,replace,pdf,pipelines,jobs,doc_render,packs}/*` | MVP done |
| Approvals & Signatures | `backend/app/modules/{approval,approvals,sign}/*`, `backend/app/api/routes/{approval_orchestration,approval_signing_v1}.py` | partial (vNext §6.9) |
| NPA & Compliance | `backend/app/modules/compliance_deadlines/*`, `backend/app/api/routes/{npa,compliance,obligations}.py`, `backend/app/domains/npa/*` | partial (vNext §19) |
| Risks | `backend/app/modules/risk/*`, `backend/app/api/routes/{risk,risk_enterprise}.py` | MVP done (PxS); v1.1 — Fine-Kinney + auto-generation |
| PPE & Warehouse | `backend/app/modules/ppe/*`, `backend/app/domains/ppe/*` | MVP done; склад — `[v1.1]` |
| Training | `backend/app/modules/training/*`, `backend/app/api/routes/{training,training_next,attestations}.py` | MVP done; внешние интеграции — `[v1.1]` |
| Briefings & Journals | `backend/app/modules/briefings/*`, `backend/app/api/routes/{briefings,journals}.py` | MVP done; kiosk — `[v1.1]` |
| Med Exams | `backend/app/api/routes/medical.py` | partial (`[v1.1]`) |
| SOUT | (часть risk + sites) | partial (`[v1.1]`) |
| Incidents | `backend/app/modules/incidents/*`, `backend/app/api/routes/incidents.py` | MVP done |
| Inspections & CAPA | `backend/app/modules/{inspections,inspection_prep,capa}/*`, `backend/app/api/routes/{inspections,prescriptions,findings...}.py` | MVP done; prescriptions — `[v1.2]` |
| Contractors & Access | `backend/app/modules/{contractors,client_portal}/*`, `backend/app/api/routes/{contractors,client_portal,portal_requests,access,integration_readiness}.py` | partial (vNext §15) |
| Equipment & Transport | `backend/app/api/routes/items.py` (частично) | `[v1.2]` |
| Ecology / Fire / Industrial / Electrical / GO-ЧС | `backend/app/api/routes/{fire-safety,fire-inspections,fire-training}.py` (только ПБ skeleton) | `[v1.2]`/`[v2.0]` |
| CRM & Billing | `backend/app/api/routes/{billing,invoices,orders,contracts,client_portal}.py` | partial (`[v1.1]`) |
| Files & Search | `backend/app/modules/{files,search}/*`, `backend/app/api/routes/{files,public_api}.py` | MVP done; universal search UI — `[v1.1]` |
| Notifications | `backend/app/modules/notifications/*`, `backend/app/api/routes/notifications.py` | MVP done |
| Workflows & Rules | `backend/app/modules/workflow/*`, `backend/app/api/routes/jobs.py` | partial (vNext §25) |
| Mobile Sync | `backend/app/modules/pwa_sync/*`, `backend/app/api/routes/pwa_sync.py` | partial (`[v1.1]`) |
| Analytics | `backend/app/modules/{analytics,export_center,projections}/*`, `backend/app/api/routes/{reports,exports,dashboard}.py` | partial (`[v1.1]`) |
| AI Copilot | — | `[v2.0]` |
| **Cross-cutting:** Operational dashboard | `backend/app/modules/operational_dashboard/*` | backend done (Phase 2.1), frontend `[v1.1]` |
| **Cross-cutting:** Data Quality | `backend/app/modules/data_quality/*` | backend MVP done (10 правил, Phase 3.1), Dashboard UI `[v1.1]` |
| **Cross-cutting:** Health checks | `backend/app/modules/health_checks/*` | done (Phase 2.2) |
| **Cross-cutting:** Audit | `backend/app/modules/audit/*`, `backend/app/domains/audit/*` | MVP done |
| **Cross-cutting:** EDO | `backend/app/modules/edo/*`, `backend/app/api/routes/edo_workflow.py` | partial (vNext §6.9) |
| **Cross-cutting:** External Registry | `backend/app/modules/external_registry/*` | partial (`[v1.1]`) |
| **Cross-cutting:** Calendar (smart calendar) | `backend/app/modules/calendar/*`, `backend/app/api/routes/calendar.py` | partial (vNext §4.4) |

Развёрнутая карта «спецификация → код → тесты» — в [`docs/spec/mapping.md`](./mapping.md). Список модулей с описаниями — в [`docs/MODULES.md`](../MODULES.md).

---

> **Помни:** при «продолжай по ТЗ» агент не должен раскапывать `vNext spec` целиком как чек-лист кода. Точка входа — этот файл (раздел A для MVP, раздел B для полного объёма) + `AI_IMPLEMENTATION_REPORT.md` + `TZ_COVERAGE_MATRIX.md`. Подробности vNext подключаются по ссылкам из раздела B.
