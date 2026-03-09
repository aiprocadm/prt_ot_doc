# FINAL GAP ANALYSIS (TZ vs code)

Дата: 2026-03-09
Основа анализа: реальная структура backend/frontend модулей, роутов, celery/jobs, тестов и миграций в репозитории.

## Метод
- Сверка требований из `docs/spec/TZ_FULL_UNIFIED.md` и `docs/spec/TZ.md` с фактическими модулями API/сервисов/моделей.
- Сверка по тестам (`tests/`, `tests/integration/`, `tests/api/`, `tests/e2e/final_regression/`).
- Отдельная проверка контрактов (OpenAPI), tenant guard, idempotency, outbox, schema consistency.

---

## 1) Tenant / Auth / RBAC-ABAC / Audit
**Статус:** partial
- Реализовано: tenant middleware, `X-Tenant` enforcement, RBAC/ABAC engine/deps/rules, audit API + immutability tests.
- Частично: field-level audit покрыт не во всех sensitive flows.
- Конфликтов с ТЗ: не найдено P0, есть P1-покрытие по ширине аудита.
- Endpoints/модели/jobs/screens: middleware `backend/app/middleware/tenant.py`, `modules/rbac_abac/*`, `modules/audit/*`, frontend pages `audit`, `access`.
- Тесты: `test_tenant_header_required`, `test_middleware_tenant`, `test_rbac_abac`, `test_audit_log_immutability`, `integration/test_audit_field_diff`.
- AC: X-Tenant mandatory — закрыт; immutable audit — закрыт; ABAC foreign access guard — частично закрыт (есть тесты на изоляцию, но не на все домены).

## 2) Domain entities
**Статус:** partial
- Реализовано: основные сущности (documents, templates, risks, ppe, training, incidents, inspections, finance, notifications).
- Частично: некоторые вертикали в MVP/skeleton режиме (warehouse depth, advanced obligations).
- AC: базовые CRUD закрыты; полнота бизнес-процессов — partial.

## 3) Templates / Render / Headers / Replace / PDF / Pipelines
**Статус:** partial
- Реализовано: templates API/service, strict by `(code, version)`, in-use delete=409, pipelines, headers, replace dry-run/apply/rollback jobs, pdf conversion service.
- Частично: corner-cases для replace + формальная проверка embedded fonts как обязательный AC.
- AC: idempotent generation закрыт, template strict закрыт, replace/pdf — частично.

## 4) EDO / Sign / Approvals
**Статус:** partial
- Реализовано: модули `edo`, `sign`, `approvals`, вебхуки.
- Частично: end-to-end SLA <=60s документирован/тестирован фрагментарно, не как единый gate.

## 5) Master data / Presets / NPA
**Статус:** done/partial
- Реализовано: NPA и пресеты присутствуют (API/pages/scripts seeds).
- Частично: полнота словарей для всех пилотных сценариев зависит от seed данных окружения.

## 6) Risks
**Статус:** done
- Реализовано: risk engine, risk services, KPI tests, domain calc tests.

## 7) PPE / Warehouse
**Статус:** partial
- Реализовано: PPE API/journals/events.
- Частично: складская глубина (партии/сертификаты/инвентаризация) ограничена MVP.

## 8) Training / Briefings
**Статус:** done/partial
- Реализовано: training services/API, completion flows.
- Частично: расширенные сертификатные/протокольные сценарии в основном через общую doc pipeline.

## 9) Incidents / Inspections
**Статус:** partial
- Реализовано: incidents, inspections, findings/prescriptions API and pages.
- Частично: глубина расследований и сквозные event hooks.

## 10) CRM / Finance-link
**Статус:** partial
- Реализовано: company/person/contractor + finance entities/tests.
- Частично: интеграционный слой внешнего CRM как полноценный коннектор не завершён.

## 11) Files / Search
**Статус:** partial
- Реализовано: files module (upload, AV, extractors), search module/indexing tests.
- Частично: прод-уровень индексационных lag SLA формально не закреплён как автотест.

## 12) API / Webhooks / CLI
**Статус:** done/partial
- Реализовано: public API, webhook routing/dispatch tests, CLI commands.
- Частично: полное выравнивание OpenAPI examples vs runtime требует постоянного drift контроля.

## 13) PWA / Offline
**Статус:** partial/missing
- Реализовано: `modules/pwa_sync/services.py` (базовый слой).
- Missing: полноценный offline UX acceptance цикл в e2e.

## 14) Reports / Dashboards
**Статус:** partial
- Реализовано: KPI reports endpoints, dashboard pages.
- Частично: полный набор экспортов/drilldown для всех ролей требует дополировки.

## 15) Billing
**Статус:** done/partial
- Реализовано: billing services/API/tests, quotas middleware.
- Частично: pilot-grade сценарии grace/suspended UX в frontend неполны.

## 16) Admin / Low-code
**Статус:** partial
- Реализовано: admin pages/outbox/billing/ops screens.
- Частично: low-code layout presets присутствуют, но без полного конструктора.

## 17) Client portal
**Статус:** partial
- Реализовано: portal dashboard/packages/documents/requests/history, API/tests.
- Частично: финальная проверка анти-утечек cross-client/cross-tenant нужна расширенным e2e.

## 18) Security / Compliance
**Статус:** partial
- Реализовано: authz docs, audit, AV hooks, token services, tenant guards.
- Частично: единый security final gate отсутствовал (добавлен в рамках final acceptance command как основа).

## 19) Backup / Restore / Ops / Observability
**Статус:** partial
- Реализовано: health/ready tests, ops docs, observability docs, backup/restore runbook материалы.
- Частично: регулярный автоматизированный restore rehearsal не закреплён скриптово в репо.

## 20) Tests / CI / Release
**Статус:** partial -> improved
- Реализовано: большой unit/integration/api набор.
- Доработано: добавлены `tests/e2e/final_regression/`, `scripts/final_acceptance.sh`, `make final-acceptance`, `scripts/verify_schema_consistency.py`.

---

## Blocker issues
1. Не обнаружены явные blocker-дефекты в базовых P0 guardrails (tenant/idempotency/template-delete).

## Critical issues
1. Неполная формализация финального e2e/UAT gate до этой задачи (устранено частично новой командой final-acceptance).
2. Неполная автоматизация schema consistency и миграционных sanity checks (добавлен baseline script).

## Medium issues
1. Ширина field-level audit по всем sensitive доменам.
2. Replace/PDF corner-cases и formal font-embed acceptance.
3. Portal anti-leakage расширить e2e для мульти-клиент сценариев.

## Low issues
1. PWA/offline acceptance матрица.
2. UX polishing для отдельных admin/reporting/large-table screens.

## Рекомендуемый порядок исправления
1. Закрыть critical contract/security gaps (tenant filters, audit depth, status enum drift).
2. Расширить e2e final regression по порталу/EDO/webhooks/SLA.
3. Довести perf+restore rehearsal до регулярного CI профиля.
4. Выполнить UX polish по major pages + доступность.
