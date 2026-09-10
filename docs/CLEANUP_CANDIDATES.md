# Repository Cleanup Candidates (TZ-6.1)

## Overview
Данный документ содержит список кандидатов на удаление/архивирование как часть TZ-6.1 (Repo hygiene).

**Процедура:**
1. Перед удалением — проверить usage в коде и других документах
2. Удалять только явно мертвые документы
3. Обновить ссылки в README если необходимо
4. Выполнить удаление в отдельном коммите с понятным сообщением

## Таблицы без модели (срез-135 → срез-138, 2026-09-10)

Опись среза-131 нашла таблицы, в которые не пишет никто. У 24 из них вердикт
был «мёртвая» — их не читал и не писал ни один экран. **Код моделей удалён,
таблицы в базе ОСТАВЛЕНЫ.** Одну из 24 — `documentgenerationjob` — пришлось
ВЕРНУТЬ: её вердикт был ошибочным (см. ниже).

Почему так: удаление таблицы уничтожает данные безвозвратно, а решение об этом
принимает владелец. Прецедент — срез-117, который так же удалил слой
жизненного цикла происшествий и оставил таблицы. Без модели данные всё равно
никому не видны, а решение можно принять позже, ничего не потеряв.

**Удалить отдельной миграцией по решению владельца** (проверив, что у
арендаторов там пусто) — 23 таблицы:

`incident_cases`, `incident_persons`, `incident_investigations`,
`incident_attachments`, `inspection_plans`, `inspection_plan_items`,
`ops_inspections`, `inspection_checklists`, `inspection_checklist_items`,
`inspection_runs`, `inspection_run_items`, `inspection_attachments`,
`prescription_items`, `corrective_action_attachments`, `asset`, `equipment`,
`edo_receipts`, `hazard_bindings`, `hazard_measures`, `reminder_rules`,
`tenant_rate_limits`, `training_protocol_items`, `risk`.

Все 23 по-прежнему вооружены RLS и перечислены в `RLS_MODEL_LESS_TABLES`
(`backend/app/core/rls_policy.py`); при сносе миграцией убрать их и из
`RLS_ENABLED_TABLES`, и из `RLS_MODEL_LESS_TABLES`.

Вместе с ними в базе остался столбец живой таблицы, ссылавшийся на мёртвую:
`inspection_prep_packages.source_inspection_id` (в коде его больше нет — его не
читала и не писала ни одна ручка).

**`documentgenerationjob` — НЕ мёртвая, а «читают, но пусто всегда».** Срез-135
удалил её по вердикту «мёртвая: работу документов ведёт PipelineRun», и полный
прогон дал 18 падений: ручки списка/детали документов отдавали 500, перенос
документов ведомых клиентов падал. Читатели: фильтр списка документов
«генерируется»/«ошибка» смотрит на `Document.job`, поле `job_id` есть в
`DocumentRead` (открытый контракт API), перенос копирует `Document.job_id`.
Заданий в неё при этом не заводит никто — фильтр «генерируется» пуст всегда,
живая генерация идёт через `DocumentJob`. Срез-138 вернул модель и столбцы;
что делать с фильтром — отдельное решение (перевести на `DocumentJob` или
убрать с экрана), записано в реестре `tests/test_tables_have_writers.py`.


## Candidates for Deletion (Pilot/Testing Artifacts)

Эти документы явно относятся к пилотным фазам разработки и не используются в текущем потоке разработки.

### Phase 1: Pilot Launch Artifacts
- `docs/CLIENT_PORTAL_PILOT_CHECKLIST.md` — пилотный чек-лист для клиентского портала
- `docs/PILOT_LAUNCH_CHECKLIST.md` — чек-лист запуска пилота
- `docs/PILOT_GO_LIVE_REPORT.md` — отчет о запуске пилота
- `docs/PILOT_METRICS.md` — метрики пилота
- `docs/PILOT_SMOKE_MATRIX.md` — smoke-тесты пилота

**Status:** Явно не используются в текущем цикле разработки (нет ссылок из других документов).

### Phase 2: Cutover Artifacts
- `docs/PRODUCTION_CUTOVER_CHECKLIST.md` — чек-лист перехода на production

**Status:** Архивная документация, может быть полезна для исторического контекста, но не для текущей разработки.

### Phase 3: Handoff/Compliance
- `docs/CODEX_HANDOFF_NEXT.md` — документ handoff от предыдущей фазы
- `docs/COMPLIANCE_REPORT.md` — compliance отчет (старый)

**Status:** Могут быть заменены на актуальные версии в docs/stabilization/ или удалены.

## Candidates for Consolidation

Эти документы имеют альтернативные версии или дублируют функционал.

### Runbook Consolidation
- `docs/runbook.md` — главный runbook
- `docs/runbook-codespaces.md` — специализированный для Codespaces
- `docs/runbooks/` — каталог с операционными playbooks (PILOT_SUPPORT_PLAYBOOK.md, TENANT_ONBOARDING.md, etc.)
- `docs/runbook/` — каталог с demo walkthroughs

**Status:** GOOD — разделение по назначению логично (demo vs ops).

### Docs/Stabilization Consolidation
- `docs/stabilization/` содержит множество файлов от разных волн:
  - RELEASE_BLOCKERS_STATUS.md
  - STABILIZATION_AUDIT.md
  - STABILIZATION_PLAN.md
  - PYTEST_FULL_RUN.md
  - Множество диагностических файлов

**Status:** Актуально для текущего статуса, ссылается из RELEASE_READINESS.md. Остаются как есть.

## Documentation Dead Code

Эти документы содержат устаревшую информацию и могут быть удалены после проверки.

- `docs/Backend_TZ.md` — старое ТЗ (заменено на docs/spec/TZ_FULL_UNIFIED.md)
- `docs/CODEX_HANDOFF_NEXT.md` — старый handoff
- `docs/LOCAL_TEST_RUNBOOK.md` — старый runbook (конфликует с docs/runbook.md)
- `docs/IMPORT_RUNBOOK.md` — специфичный для импорта (мало используется)
- `docs/ENVIRONMENT.md` — может быть заменено на docs/SETUP.md
- `docs/ENV_REFERENCE.md` — может быть заменено на docs/SETUP.md

## Recommended Cleanup Order

### Wave 1 (Safe) ✅ COMPLETED (2026-05-01)
Удалены явно unused пилотные документы:
- ✅ `docs/CLIENT_PORTAL_PILOT_CHECKLIST.md`
- ✅ `docs/PILOT_LAUNCH_CHECKLIST.md`
- ✅ `docs/PILOT_GO_LIVE_REPORT.md`
- ✅ `docs/PILOT_METRICS.md`
- ✅ `docs/PILOT_SMOKE_MATRIX.md`

### Wave 2 (After Verification) ✅ COMPLETED (2026-05-01)
Удалены старые runbooks и документы:
- ✅ `docs/LOCAL_TEST_RUNBOOK.md` (удалено)
- ✅ `docs/Backend_TZ.md` (удалено, заменено на spec/TZ_FULL_UNIFIED.md)
- ✅ `docs/CODEX_HANDOFF_NEXT.md` (удалено)
- ✅ `docs/COMPLIANCE_REPORT.md` (удалено)
- ✅ `docs/PRODUCTION_CUTOVER_CHECKLIST.md` (удалено)
- ✅ `docs/IMPORT_RUNBOOK.md` (удалено)
- ✅ `docs/ENVIRONMENT.md` (удалено)
- ✅ `docs/ENV_REFERENCE.md` (удалено, консолидировано в docs/SETUP.md)

### Wave 3 (After Consolidation)
- Объединить `docs/ENVIRONMENT.md` и `docs/ENV_REFERENCE.md` в `docs/SETUP.md`
- Удалить дубликаты после консолидации

### Wave 4 (TZ canonicalization, 2026-05-04) 🟡 IN PROGRESS

После того как `docs/spec/TZ_FULL_UNIFIED.md` стал каноническим и единственным источником истины «по ТЗ» (с разделами A — MVP, B — полный объём vNext, C — статус, D — фазы, E — правила доработки), часть документов превращается в дубликаты или историко-справочные. Действия:

- **Помечены deprecated, кандидаты на удаление в следующей волне:**
  - `docs/NEXT_FEATURES.md` — содержание полностью покрыто разделом B `TZ_FULL_UNIFIED.md` и `docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md §7..§30`. Удалить после убирания внешних ссылок.
  - `docs/SPEC_TRACEABILITY_MATRIX.md` — функция перекрыта `docs/audit/TZ_COVERAGE_MATRIX.md`; преобразовать в навигационный индекс или удалить.
  - `docs/spec_compliance_report.md` / `docs/p1_compliance_report.md` — статус истинный отслеживается в `TZ_COVERAGE_MATRIX.md` + `RELEASE_READINESS.md` + `GAP_REPORT.md`. Архив, не использовать для приёмки.
- **Оставить как историко-справочное (без новых ссылок):**
  - `docs/spec/TZ.md` — первая версия ТЗ (v1.0, 2025-11-05). Хранить, не обновлять, не использовать для приёмки.
  - `docs/Backend_TZ.md` (уже удалён в Wave 2).
- **Не удалять, но убедиться, что не плодят альтернатив:**
  - `RB_BLOCKERS_EXECUTION_READY.md`, `SESSION_SUMMARY_PHASE_A_COMPLETE.md`, `PHASE_2_WEEK_3_PARTIAL_COMPLETION.md`, `wave-37-rb-guide.md` — снимки прошлых волн в корне. Не дублировать формат `AI_IMPLEMENTATION_REPORT.md`. Кандидаты на перенос в `docs/archive/` после ревью.
  - `docs/facts.md` — снимок ранней волны (устаревшие debts). Помечен `DEPRECATED` 2026-05-04, кандидат на удаление в Wave 4.

Перед удалением — `grep -r "DOCUMENT_NAME" .` (см. блок Validation ниже) и обновление ссылок в `README.md`/`docs/README.md`/`docs/spec/README.md`.

## Validation

Перед удалением каждого документа:

```bash
# Check for references
grep -r "DOCUMENT_NAME" . --include="*.md" --include="*.py" --exclude-dir=".git"

# Check for links
grep -r "docs/DOCUMENT_NAME" . --include="*.md" --exclude-dir=".git"
```

## Root-Level Stale Wave Reports (уборка 2026-08-06)

Отчёты давно закрытых волн стабилизации, лежащие в корне репозитория. На них нет
ссылок из кода, CI, Makefile и живых доков (проверено rg по всему репо + адверсарная
перепроверка вторым агентом); содержательно не менялись с границы видимой истории
(2026-07-16, импорт-коммит). НЕ входят в обязательный список
`tests/e2e/test_release_candidate_docs.py` и `scripts/repo_audit.py` — в отличие от
ACCEPTANCE_TEST_MATRIX / GAP_REPORT / RELEASE_READINESS / KNOWN_LIMITATIONS /
CHANGED_PATHS_AND_RENAMES, которые трогать нельзя.

- `ARCHITECTURE_DECISIONS_STABILIZATION.md` — решения волны стабилизации, влиты в код
- `CHANGED_MODULES_AND_DECISIONS.md` — журнал изменённых модулей той же волны
- `CONFIGURATION_HARDENING.md` — отчёт по hardening конфигурации (выполнен)
- `PHASE_2_WEEK_3_PARTIAL_COMPLETION.md` — промежуточный отчёт Phase 2 Week 3
- `RB_BLOCKERS_EXECUTION_READY.md` — план снятия RB-блокеров (снятие завершено)
- `REGRESSION_RISKS_AND_MITIGATIONS.md` — риски регрессии волны стабилизации
- `REGRESSION_TEST_MATRIX.md` — матрица регрессионных тестов той волны
- `RUNBOOK_STABILIZATION.md` — runbook волны стабилизации
- `SESSION_SUMMARY_PHASE_A_COMPLETE.md` — итог сессии Phase A
- `STABILIZATION_AUDIT.md` — аудит стабилизации (закрыт)
- `STABILIZATION_PLAN.md` — план стабилизации (выполнен)
- `TEST_COVERAGE_GAPS.md` — пробелы покрытия на момент той волны (устарели)
- `wave-37-rb-guide.md` — гайд волны 37

**Status:** кандидаты на удаление решением владельца; до удаления можно перенести в
`docs/archive/`.

## Summary

**Total candidates:** ~15 documents + 13 root-level wave reports (2026-08-06)
**Safe deletions:** 5 pilot documents
**Consolidation candidates:** 10 documents
**Keep as is:** Stabilization docs, spec docs, runbooks/runbook structure

---

Last updated: 2026-08-06
Next review: After root-level wave reports decision
