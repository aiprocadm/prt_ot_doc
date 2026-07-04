# SPEC ↔ CODE SYNC (2026-07-04)

Прямая сверка канонического ТЗ (`docs/spec/TZ_FULL_UNIFIED.md` разд. A/B + `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`) с **фактическим кодом** ветки `main`.

- **Updated on (UTC):** 2026-07-04
- **Метод:** код = арбитр. Git-предки веток (`git rev-list`), прямой осмотр `backend/app/modules|domains|api`, `frontend/src/{pages,features}`, `.github/workflows/`, зависимостей. Документы — как проверяемые утверждения.
- **База сверки:** `main` @ `d2529c85` (merge PR #722, СИЗ-склад инвентаризация). Рабочая ветка побайтно равна `main`.
- **Статус-словарь:** `done` / `substantial` / `partial` / `skeleton` / `none`.
- **Канон статусов остаётся за:** `docs/audit/TZ_COVERAGE_MATRIX.md` (MVP), `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (блокеры), реконсиляция Section B в роадмапе. Этот файл — навигационный снимок сверки, не заменяет канон.

---

## 1. Расхождения «документ ↔ код»

Во всех найденных случаях документация **занижает / устарела относительно кода** (не наоборот). Правки внесены точечно в соответствующие файлы.

| Область | Документ говорил | Реально в коде (evidence) | Внесённая правка |
|---|---|---|---|
| **Workflow-движок** (P10-10) | роадмап: `❌ not started` | **substantial**: `backend/app/modules/workflow/` (~1.4k LOC — граф start/task/approval/condition/timer/notification/webhook/end, версии draft/published/archived, инстансы, задачи, таймлайн, SLA, эскалация); смонтирован `api/v1/route_groups.py:85,180`; потребители `analytics`/`projections`/`domain_ticks` | роадмап: строка P10-10 → `partial`; summary-счёт 4→3 not started, 8→9 partial |
| **CI** | CLAUDE.md + RELEASE_READINESS: «отключён с PR #598, `.yml.disabled`» | **включён**: PR #641 (`re-enable GHA W0`) + PR #656 (`workflow_dispatch + baseline re-verify`); в `.github/workflows/` 5 активных `.yml` (`ci`, `e2e-smoke`, `final-acceptance`, `perf-baseline`, `restore-drill`) | CLAUDE.md «CI status» + RELEASE_READINESS evidence-policy строка обновлены; local-evidence по-прежнему канонический gate (REL-1) |
| **Уведомления/эскалация** (RC-011) | KNOWN_LIMITATIONS: `missing` | **done**: `modules/notifications/{delivery.py,providers/}` — цепочка email→telegram→in-app, честный статус, `notifications.dispatch_pending` beat; канон `RELEASE_BLOCKERS_STATUS` уже `done` (2026-07-01). Флаг `NOTIFICATIONS_DELIVERY_ENABLED` по умолчанию OFF | KNOWN_LIMITATIONS: RC-011 `missing`→`done` |
| **Медосмотры** (P10-03) | роадмап «остаётся: контингент/психиатрия/направления/отстранение» | **substantial**: контингент-реестр (`medical/contingent`), `MedicalExamKind.PSYCHIATRIC`, `MedicalReferral`-FSM, `MedicalSuspension`-FSM (`domains/medical/lifecycle.py`) | роадмап sync-note (все 4 в коде; остаётся полнота, не отсутствие) |
| **НПА/Compliance** | Прил.4 ТЗ: `partial (vNext §19)` | **substantial**: реестр `NpaAct/NpaRevision/NpaClause`, impact-analysis с bindings (`domains/npa/impact.py`), генерация задач-обязательств, дедлайны (`compliance_deadlines`) | роадмап sync-note |
| **Клиентский кабинет** (P10-02) | «остаётся: клиентский кабинет» | **есть**: 5 страниц `frontend/src/pages/client-portal/` (Dashboard/Packages/Documents/History/Requests) | роадмап sync-note (остаётся reseller-портал + trial/sandbox) |
| **Ветки `feat/*`** | журнал handoff: «НЕ влита» (post-1/2, rc-014, sout-5/6, ppe-movements/inventory) | **всё влито**: `git rev-list --count main..<branch>` = 0 (`ahead_of_main=0`) для всех; это устаревшие локальные ветки | без правки доков (журнал — справочный, снимки на момент сессии) |

---

## 2. Что реально осталось выполнить

MVP (ТЗ разд. A) и vNext Phase 1–9 закрыты и работают в коде (ядро проверено: `services/idempotency.py`, `services/outbox.py` +DLQ, `modules/replace/service.py` rollback, `modules/pipelines/orchestrator.py`, `middleware/tenant.py`). Остаток — vNext Section B / Phase 10 + эксплуатационные хвосты.

### A. Не начато (кода нет)

| Пункт | ТЗ | Проверка |
|---|---|---|
| SSO / SAML 2.0 / OIDC / JIT | P10-13, B.31 | нет библиотек (saml/authlib/oidc), auth = локальный JWT |
| Вертикали: ПромБез / Экология / ГО-ЧС | P10-11, B.19 | экология = только enum `waste_and_ecology`; ПБ = фронт-скелет поверх общих эндпоинтов; industrial/ГО-ЧС = 0 |
| Терминалы / kiosk / биометрия / СКУД / видеоаналитика (CV) / AI Copilot | P10-15, B.20/21/25 | нет модулей и нет AI-зависимостей (openai/anthropic/langchain) |
| Smart Recommendations | P10-10, B.24 | только static-условия в workflow, отдельного движка нет |
| Reseller / white-label портал, trial/sandbox-изоляция | P10-02, B.22 | нет reseller-роутов/партнёрских тенантов |
| Report-builder UI (кастомные отчёты, scheduled delivery) | P10-07, B.23 | только фикс-KPI `reports/kpi`, конструктора нет |
| Equipment/Asset/ОПО/Транспорт-реестр | P10-09, B.16 | только generic `api/routes/items.py` |
| Site/объект 360°-карточка (фронт) | Phase 3, B.4 | есть только `EmployeeCardPage.tsx`, `SiteCardPage` нет |
| СИЗ-склад: перемещения между локациями, поставщики, бюджет безопасности, мобильная выдача | P10-06, B.11 | нет location/transfer/supplier/budget-моделей и mobile-эндпоинтов |
| МЧД + роуминг ЭДО | P10-12, B.5 | нет модели/enum/роутов |

### B. Частично — есть фундамент, нужно достроить

| Пункт | Есть / чего нет |
|---|---|
| КЭП/УНЭП (P10-12) | enum `SignatureType.KEP/UNEP` есть, провайдеры не подключены («появятся при интеграции»); ПЭП рабочий, квитанции есть |
| Mobile / offline (Phase 7.2) | бэкенд PWA-sync + conflict resolution готов; на фронте SW-регистрация есть, **нет IndexedDB-очереди и UI разрешения конфликтов** |
| i18n (P10-14) | инфраструктура `core/i18n.py` + `frontend/src/i18n/`; полных 5+ языков и переводов UI/API/email нет |
| Комитеты (P10-01) | срез-1 (модели+API 15 эндпоинтов+тонкий UI); нет голосования/кворума/нумерации протоколов/KPI (срез-2) |
| Управленческие дашборды (P10-07) | операционные есть (10+ эндпоинтов); роле-специфичных управленческих нет |

### C. MVP — эксплуатационные хвосты (не код)

| Пункт | Суть |
|---|---|
| Backfill PG enum-меток | БД до iter-49 хранят UPPER member-name (`user.role`, `document.status`) → нужен `UPDATE … lower(col)` перед промоушеном. Свежая PG корректна |
| Уведомления выключены флагом | `NOTIFICATIONS_DELIVERY_ENABLED` default OFF; SMS-провайдера нет |
| Phase 0 baseline re-run | инфраструктура готова; канонический прогон run `27508869071` (2026-06-14, 3138 тестов) уже был — часть доков ещё помечает pending |

---

## 3. Внесённые правки доков (2026-07-04)

- `CLAUDE.md` — секция «CI status» переписана (workflow-файлы включены; local-evidence = канонический gate).
- `KNOWN_LIMITATIONS.md` — RC-011 `missing`→`done`; дата обновлена.
- `RELEASE_READINESS.md` — evidence-policy строка синхронизирована (workflow'ы re-enabled, local-evidence канон).
- `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` — P10-10 `not started`→`partial`; summary-счёт; sync-note под Section B (медосмотры/НПА/клиент-кабинет).

## Cross-links

- ТЗ: `docs/spec/TZ_FULL_UNIFIED.md`
- MVP-матрица: `docs/audit/TZ_COVERAGE_MATRIX.md`
- Роадмап (Section B реконсиляция): `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`
- Блокеры (канон): `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`
- Вердикт релиза: `RELEASE_READINESS.md`
- Ограничения: `KNOWN_LIMITATIONS.md`
