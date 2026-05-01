# Repository Cleanup Candidates (TZ-6.1)

## Overview
Данный документ содержит список кандидатов на удаление/архивирование как часть TZ-6.1 (Repo hygiene).

**Процедура:**
1. Перед удалением — проверить usage в коде и других документах
2. Удалять только явно мертвые документы
3. Обновить ссылки в README если необходимо
4. Выполнить удаление в отдельном коммите с понятным сообщением

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

## Validation

Перед удалением каждого документа:

```bash
# Check for references
grep -r "DOCUMENT_NAME" . --include="*.md" --include="*.py" --exclude-dir=".git"

# Check for links
grep -r "docs/DOCUMENT_NAME" . --include="*.md" --exclude-dir=".git"
```

## Summary

**Total candidates:** ~15 documents
**Safe deletions:** 5 pilot documents
**Consolidation candidates:** 10 documents
**Keep as is:** Stabilization docs, spec docs, runbooks/runbook structure

---

Last updated: 2026-05-01
Next review: After wave 3 cleanup completion
