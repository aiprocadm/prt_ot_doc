# FINAL DEFECT BURNDOWN BACKLOG

## FB-001
- severity: critical
- area: Contract hardening / audit
- symptom: не все sensitive изменения гарантированно дают field-level diff в audit.
- expected behavior by spec: любое чувствительное изменение фиксируется с diff.
- actual behavior: покрытие есть, но не равномерно по доменам.
- likely root cause: исторически разнотипные сервисы и частично централизованный writer.
- proposed fix: унифицировать сервисный декоратор audit-diff + интеграционные тесты по доменам.
- test to add: `tests/integration/final_acceptance/test_sensitive_field_audit.py`
- migration needed: no
- frontend/backend/both: backend

## FB-002
- severity: critical
- area: Replace/PDF
- symptom: corner-cases DOCX (сложные textbox/shape + fonts) могут вести к расхождениям.
- expected behavior by spec: dry-run/apply/rollback + PDF с embedded font.
- actual behavior: базовые кейсы закрыты, угловые требуют расширения.
- likely root cause: ограничения docx/xml engine + окружение LO.
- proposed fix: добавить golden-файлы и интеграционные regression tests.
- test to add: `tests/integration/final_acceptance/test_replace_pdf_corner_cases.py`
- migration needed: no
- frontend/backend/both: backend

## FB-003
- severity: major
- area: Client portal security
- symptom: недостаточный e2e охват cross-client leakage сценариев.
- expected behavior by spec: клиент видит только собственные данные.
- actual behavior: базовые тесты есть, но матрица неполная.
- likely root cause: фокус на API-unit/integration вместо role-journey e2e.
- proposed fix: расширить e2e набор мультиклиентными фикстурами.
- test to add: `tests/e2e/final_regression/test_client_portal_isolation.py`
- migration needed: no
- frontend/backend/both: both

## FB-004
- severity: major
- area: OpenAPI drift
- symptom: риск рассинхронизации examples/enums между runtime и spec.
- expected behavior by spec: OpenAPI полностью соответствует API.
- actual behavior: есть валидация, но нужен регулярный final gate.
- likely root cause: быстрые инкременты модулей.
- proposed fix: запуск `tests/contract/test_openapi_contract.py` и `scripts/contract/validate.py` в final-acceptance/CI.
- test to add: расширенный contract snapshot compare.
- migration needed: no
- frontend/backend/both: both

## FB-005
- severity: major
- area: Ops / restore
- symptom: restore rehearsal не закреплён автоматизированным сценарием.
- expected behavior by spec: backup/restore verified.
- actual behavior: документировано, но не всегда прогоняется как gate.
- likely root cause: dependency on infra.
- proposed fix: scripted dry-run restore в stage.
- test to add: `tests/integration/final_acceptance/test_restore_rehearsal.py` (env-guarded).
- migration needed: no
- frontend/backend/both: backend

## FB-006
- severity: minor
- area: Frontend UX
- symptom: в части страниц не хватает retry/empty/help states.
- expected behavior by spec: понятные блокировки/ошибки/retry.
- actual behavior: реализовано частично.
- likely root cause: неоднородность старых страниц.
- proposed fix: unify page-state компоненты и route-level guards.
- test to add: frontend RTL smoke per major page state.
- migration needed: no
- frontend/backend/both: frontend
