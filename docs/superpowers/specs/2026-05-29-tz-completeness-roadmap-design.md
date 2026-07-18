# План доработок «по ТЗ» — приоритизированный roadmap (полнота раздела B)

- **Дата:** 2026-05-29
- **Статус:** проект (design / proposal), ожидает ревью пользователя
- **Тип:** аналитика + предложение очерёдности. **НЕ конкурирующий roadmap.**
- **Канон ТЗ:** [`docs/spec/TZ_FULL_UNIFIED.md`](../../spec/TZ_FULL_UNIFIED.md) (раздел A — MVP, B — полный объём).
- **Драйвер приоритизации (решение пользователя):** *полнота ТЗ, строго по порядку фаз 2→3→7→9→10, без бизнес-уклона.* Внутри полного объёма под-очерёдность задаётся тегами версий `[v1.1] → [v1.2] → [v2.0]`.

> **Дисциплина каноничности (раздел G ТЗ — «без дублей roadmap»).** Этот файл — design-артефакт брейншторма. Он **не** заменяет канонический план. Принятые решения по очерёдности и развёртка Phase 10 вносятся в [`docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`](../../roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md); статус MVP — только в [`docs/audit/TZ_COVERAGE_MATRIX.md`](../../audit/TZ_COVERAGE_MATRIX.md). При расхождении побеждают канонические файлы.

---

## 1. Ключевая находка анализа

Большая часть «vNext»-объёма в дорожной карте — это **backend, который уже отгружен**, а сессии 36–53 лишь «пинили» его контрактными тестами (повторяющаяся формулировка в плане: *«engine was already shipped, this pins the contract»*). Незакрытого **кода** существенно меньше, чем фаз. Реальный остаток группируется в 5 категорий:

| Категория | Содержание | Исполнимость автономной AI-сессией |
|---|---|---|
| Хвосты MVP-матрицы | склад СИЗ (`missing`), предписания (`partial`), coverage-gate ≥85% (`missing`) | 🟦 код (2) + ⚙️ CI-config (gate) |
| Frontend для готовых backend'ов | Command Center UI (Ph2.1), Health UI (Ph2.2), карточка объекта (Ph3), field UX (Ph7.2) | 🟨 frontend |
| Незавершённый Phase 1.3 | tenant-isolation audit: 5 удалённых тестов + чек-лист границ + док | 🟦 код |
| Postgres/infra-зависимое | slow-query (EXPLAIN), партиционирование, Redis service-cache (Ph9.1/9.2) | 🟥 нужен staging-Postgres |
| Реально не построенное (Phase 10 / полный объём B) | SSO/SAML, i18n/white-label, CRM, AI, вертикали, наряды-допуски, equipment, комитеты, workflow-engine, kiosk, видеоаналитика + добивка partial-контекстов | 🟦 код, но ~15 под-проектов |

**Дефект дорожной карты, который этот план закрывает:** `PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` детально расписывает Phase 0–9, но **Phase 10 = всего 2 задачи (SSO + white-label)**, тогда как раздел **B** канона перечисляет ещё ~13 крупных контуров. Для «полноты ТЗ» Phase 10 **разворачивается** до раздела B (см. §4).

**Условные обозначения исполнимости:** 🟦 backend-код · 🟨 frontend · 🟥 нужен staging/infra · ⚙️ операционное (зона пользователя: git/CI/деплой).

---

## 2. Каркас волн (по порядку фаз)

| Волна | Фаза ТЗ | Содержание | Тег | Размер | Зависимости |
|---|---|---|---|---|---|
| **W0** | Phase 0 | baseline re-verification в чистом окружении + re-enable CI + слить висящие PR / `alembic merge_heads` / чистка веток (iter-30/31/37) | ⚙️ | S | — |
| **W-A** | MVP-хвосты | склад СИЗ skeleton · lifecycle предписаний · coverage-gate ≥85% → матрица 100% `done` | 🟦 + ⚙️ | S–M | — |
| **W1** | Phase 1.3 | tenant-isolation audit: перестроить 5 удалённых тестов + чек-лист 20+ границ + `docs/TENANT_ISOLATION_BOUNDARIES.md` | 🟦 | M | — |
| **W2** | Phase 2 | Command Center UI (виджеты алертов) + Health-status UI (drill-down) — backend готов | 🟨 | M | W0 (для realtime/perf-проверки) |
| **W3** | Phase 3 | Unified Site Card (backend-агрегат + UI, по образцу EmployeeCard) + добивка правил Data Quality до полного списка | 🟦 + 🟨 | M | — |
| **W4** | Phase 7.2 | field UX: мобильные чек-листы · фото + гео + timestamp · подпись на устройстве (offline-aware, поверх готового pwa_sync) | 🟨 | M | — |
| **W5** | Phase 9 (ост.) | slow-query identification (EXPLAIN ANALYZE) · date-партиционирование (events/audit_log/documents) · Redis service-cache · аудит единообразия Cache-Control | 🟥 | M–L | staging-Postgres |
| **W6** | Phase 10 = разд. B | развёртка в ~15 под-проектов; очерёдность по тегу версии (см. §4) | 🟦 (крупно) | XL | по тегам |

### Очерёдность исполнения

Строго по фазам: **W0 → W-A → W1 → W2 → W3 → W4 → W5 → W6**.

Прагматическая оговорка: W0 — операционная (git/CI/деплой), её исполняет пользователь, она не идёт через цикл брейншторм→writing-plans. Поэтому **первый кодовый под-проект для детального дизайна — W-A, элемент «склад СИЗ skeleton»** (§5).

---

## 3. Детализация волн W-A … W5

### W-A — Хвосты MVP-матрицы (→ 100% `done`)
Три независимых элемента, каждый — отдельный цикл writing-plans:
- **`TZ-3.2-V11-01` склад СИЗ skeleton** `[v1.1]` `missing` → детально в §5. Первый под-проект.
- **`TZ-3.4-V12-01` предписания (prescriptions) lifecycle** `[v1.2]` `partial` → финализировать workflow статусов + acceptance-док. Backend-роут `backend/app/api/routes/prescriptions.py` уже существует (ETag добавлен в S51); остаётся доопределить жизненный цикл (исполнители, дедлайны, доказательства, повторные проверки, эскалации, % закрытия) — `vNext §14.3`.
- **`TZ-6.3-V11-01` coverage-gate ≥85%** `[v1.1]` `missing` → scoped coverage-job для `core/domain/services` + документированный «climb plan». Частично ⚙️ (CI-config), активируется вместе с W0 (re-enable CI).

**Acceptance W-A:** все строки `TZ_COVERAGE_MATRIX.md` со `status ∈ {missing, partial}` переведены в `done` либо явно переотегированы с обоснованием.

### W1 — Tenant Isolation Audit (Phase 1.3)
- Перестроить 5 unit-тестов изоляции, удалённых как «never worked» (см. `KNOWN_LIMITATIONS.md` §«Test-suite limitations», iter-17b): audit_log / workflow_events / webhook_delivery / outbox / notification — с корректными путями импорта (`app.models.models` / `app.models.notifications`) и `await` на async-сессии.
- Чек-лист 20+ критических границ (queries / mutations / file access / event publishing / integrations).
- `docs/TENANT_ISOLATION_BOUNDARIES.md` с доказательствами (файл уже есть — дополнить).
- **Acceptance** (`vNext §35`, F.8 косвенно): негативные тесты на cross-tenant утечку зелёные; чек-лист покрыт.

### W2 — Operational Dashboard / Health UI (Phase 2, frontend)
- Backend готов: `/api/v1/operational/dashboard` (агрегатор алертов, 12+ тестов) и `/api/v1/health/comprehensive`.
- **Остаётся frontend:** страница Command Center с виджетами (просроченные, заблокированные согласования, проблемные документы, ошибки интеграций, high-risk объекты, незакрытые предписания, истекающие обучения/медосмотры/СИЗ, offline-конфликты, неназначенные задачи, health-предупреждения tenant'а); polling/WS обновление; health-страница с drill-down per service.
- **Acceptance** (план Ph2.1): загрузка < 2 c при 1000+ элементов; роле-зависимая видимость.

### W3 — Unified Site Card + Data Quality добивка (Phase 3)
- **Site Card** (`vNext §5.3`, B.4): read-only агрегат `GET /api/v1/sites/{id}` (объект → подразделения/рабочие места, риски, СОУТ, медосмотры, инциденты, проверки, документы, аудит) + UI по образцу `EmployeeCardPage.tsx` (11 табов, Sessions 19–21). Без дублирования данных — relationships, не копии.
- **Data Quality:** расширить движок правил (`backend/app/modules/data_quality/`, сейчас 7 правил) до полного списка `vNext §5.4` (логические конфликты, integration-mismatch, документы не готовы к генерации, допуски невалидны для подрядчиков).
- **Acceptance** (F.4 косвенно): нет противоречий между табами; правила покрыты тестами.

### W4 — Field-Specific Workflows (Phase 7.2, frontend/mobile)
- Поверх готового backend offline-sync (`app.modules.pwa_sync`, 28 тестов, S43): мобильные чек-листы (site audit / equipment check / incident report), фото с гео + timestamp, подпись на устройстве.
- **Обязательно offline-aware** (правило §36.3): очередь действий, sync при reconnect, conflict UI (бэкенд-контракт конфликтов уже есть).
- **Acceptance** (F.9): approve/sign с мобильного; audits/checklists/incidents/СИЗ-issue в field-mode; offline-очередь и conflict UI работают.

### W5 — Performance & Scale остаток (Phase 9)
- 🟥 **Требует staging-Postgres** (на SQLite-тестах не закрывается):
  - slow-query identification — `EXPLAIN ANALYZE` workflow на prod-объёме;
  - date-партиционирование (`events`, `audit_log`, `documents`);
  - Redis service-level read-through cache (TTL/eviction/warm-up + политика инвалидации) для горячих чтений;
  - аудит единообразия `Cache-Control` + докатить ETag на оставшиеся list-эндпоинты (аддитивно, через `compute_list_etag`).
- **Acceptance** (`vNext §31.4`): API p95 ≤ 1 c; batch 30 DOCX→PDF p95 ≤ 60 c; 1000 одновременных пользователей в аренде.

---

## 4. Развёртка Phase 10 → раздел B (≈15 под-проектов)

Очерёдность — по тегу версии (`[v1.1]` раньше `[v1.2]` раньше `[v2.0]`). Каждый под-проект — отдельный цикл брейншторм→спец→план.

### Группа [v1.1] (ближний полный объём)
| ID | Под-проект | Канон |
|---|---|---|
| P10-01 | Комитеты / комиссии / заседания (повестки, протоколы, голосование, KPI исполнения) | B.17 / `vNext §18` |
| P10-02 | CRM-контур + клиентский кабинет + trial/demo/sandbox + reseller/white-label-портал | B.22 / `vNext §23` |
| P10-03 | Медосмотры (полный контур: контингент, периодические/предварительные/психиатрия, направления, отстранение) | B.8 / `vNext §9` |
| P10-04 | СОУТ (карты, классы, вредные факторы, связь с СИЗ/медосмотрами/рисками) | B.9 / `vNext §10` |
| P10-05 | Подрядчики и допуск (readiness engine, внешний кабинет, guided collection) — добивка | B.14 / `vNext §15` |
| P10-06 | СИЗ: склад полный + бюджет безопасности + мобильная выдача (расширение W-A skeleton) | B.11 / `vNext §12.3–12.5` |
| P10-07 | Analytics frontend (операционные + управленческие дашборды, report builder UI) | B.23 / `vNext §24` |

### Группа [v1.2] (средний горизонт)
| ID | Под-проект | Канон |
|---|---|---|
| P10-08 | Наряды-допуски и работы повышенной опасности | B.15 / `vNext §16` |
| P10-09 | Equipment / Asset / Транспорт / ОПО / Электробезопасность | B.16 / `vNext §17` |
| P10-10 | Workflow / Rules / Smart Recommendations engines | B.24 / `vNext §25` |
| P10-11 | Вертикали: ПромБез · Экология · ГО-ЧС (ПБ — skeleton уже есть) | B.19 / `vNext §20` |
| P10-12 | ЭДО/подпись полный контур (КЭП/УНЭП/МЧД, роуминг, квитанции) + НПА/compliance management | B.5 §6.9–6.10 / B.18 / `vNext §19` |

### Группа [v2.0] (дальний горизонт)
| ID | Под-проект | Канон |
|---|---|---|
| P10-13 | SSO / SAML 2.0 / OIDC + JIT provisioning (роадмап-Task 10.1) | `vNext §32` / `§30.2` |
| P10-14 | White-label + i18n 5+ языков (роадмап-Task 10.2) | `vNext §34` (white-label/sellability) / `§29` (i18n frontend) |
| P10-15 | Терминалы/kiosk/биометрия/СКУД · видеоаналитика/CV · AI Copilot | B.20 / B.21 / B.25 |

> Примечание: SSO/i18n канон тяготеет к enterprise-готовности (`[full]`), но в дорожной карте они уже выделены как Task 10.1/10.2 — оставляем их явными узлами; конкретный тег внутри [v2.0]-группы уточняется при заходе в под-проект.

---

## 5. Первый под-проект (детально): W-A · Склад СИЗ skeleton (`TZ-3.2-V11-01`)

### 5.1 Фактическое состояние (по коду, не по матрице)
- **Модель-сирота:** `WarehousePPE(item_name, quantity, location)` ([backend/app/models/models.py:2183](../../../backend/app/models/models.py)) — без FK на каталог СИЗ, без партий/сертификатов/инвентаризации, **без API** (grep `warehouse|stock|inventory` по `backend/app/api` → пусто).
- **Фасадная страница:** `frontend/src/pages/warehouse/WarehousePage.tsx` называется «Склад СИЗ», но рендерит `opsApi.getPpeOverview()` — *каталог СИЗ + истекающие выдачи*, без реальных остатков/партий/склада.
- **Готовая опора:** PPE-каталог (`PPEItem`, `PPENorm`) + роуты `/api/v1/ppe/{items,issues}` (с ETag, S51); модуль `backend/app/modules/ppe/services.py`.

### 5.2 Объём skeleton (`[v1.1]`, минимально достаточный)
Из `vNext §12.3` берём для skeleton: **номенклатура, партии (batch), остатки (stock level), сертификаты, базовая инвентаризация (count)**. Откладываем (явно, в матрицу): перемещения/резервирование, поставщики, прогноз дефицита — `[v1.1]+`/`[v1.2]`.

**Минимальная аддитивная схема (новые таблицы, не трогаем сироту):**
- `ppe_stock_batch` — партия: FK→`PPEItem`, `batch_no`, `quantity`, `received_at`, `certificate_no`, `certificate_expires_at`, `location`, tenant-scoped.
- (опц.) `ppe_inventory_count` — инвентаризация: дата, по локации, факт vs учёт.
- Остаток позиции = агрегат по партиям (вьюха/сервис-метод), не отдельная денормализованная таблица.

**Решение по сироте `WarehousePPE`:** не удалять (правило additive-миграций), пометить как legacy-stub; writing-plans проверит usage и решит «расширить vs deprecate в W6/P10-06». В skeleton — новые таблицы.

**Endpoints (по образцу ppe-роутов, с `compute_list_etag`):**
- `GET/POST /api/v1/ppe/stock/batches`, `GET/PATCH /api/v1/ppe/stock/batches/{id}`
- `GET /api/v1/ppe/stock/levels` (агрегат остатков по позициям/локациям)
- (опц.) `GET/POST /api/v1/ppe/stock/inventory`

**Frontend:** заменить фасад в `WarehousePage.tsx` на реальный warehouse-API (остатки, партии, ближайшие истечения сертификатов), сохранив существующий вид списка/поиска.

### 5.3 Acceptance (W-A · склад)
- Минимальная схема + миграция (additive) + endpoints + listing UI работают end-to-end.
- ETag на list-эндпоинтах через `compute_list_etag`; tenant-isolation тесты (cross-tenant 404/no-leak).
- Unit + API тесты (≥ паттерн ppe-контрактов); OpenAPI обновлён; seed-данные для демо.
- `TZ-3.2-V11-01` в матрице → `done` (или `partial` с явным остатком на P10-06).

### 5.4 Шесть вопросов (§36.4)
1. **Роль:** кладовщик / специалист ОТ / снабжение.
2. **Сценарий:** учёт партий СИЗ, контроль сроков сертификатов, остатки перед выдачей.
3. **Данные:** каталог `PPEItem` (есть) + новые партии/остатки; источник — ручной ввод + (позже) импорт.
4. **Offline/сбой:** список — кэш ETag; запись — стандартный online-путь (offline для выдачи — отдельный mobile-сценарий W4/P10-06).
5. **Обратная связь:** бейджи риска истечения, пустые состояния, ошибки с retry (паттерн `WarehousePage` уже есть).
6. **Feature flag:** `FEATURE_PPE_WAREHOUSE` (tenant-scoped), без глобального рефактора.

---

## 6. Обязательные правила доработки (§E канона / §36 vNext)

Применяются ко всем волнам: не ломать рабочие модули; не удалять API без слоя совместимости; новые функции — через feature flags; **additive миграции**; tenant isolation на всех границах; bounded contexts через события; тяжёлые операции — в async workers; unit/integration/e2e тесты; OpenAPI + CHANGELOG + seed; correlation-id; строгая типизация (backend + frontend).

---

## 7. Следующий шаг

1. **Ревью этого спека пользователем.**
2. Применить решения в канон: развернуть Phase 10 в `PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`; зафиксировать очерёдность волн.
3. Запустить **writing-plans** для первого под-проекта — **W-A · склад СИЗ skeleton** (§5).
4. Дальше — по порядку волн, каждая значимая единица: брейншторм → спец → план → реализация → обновить матрицу/handoff.
