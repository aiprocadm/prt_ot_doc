# KNOWN LIMITATIONS

## 1. Browser-level e2e breadth
Полный browser-driven e2e пакет по всем критичным сценариям еще не доведен до той же ширины, что и backend/integration acceptance coverage. Для текущего RC опора сделана на API/e2e/integration tests и runbook evidence.

## 2. Performance baselines are smoke-grade
`scripts/perf/api_load.py` и `scripts/perf/README.md` дают воспроизводимую smoke/load foundation, но не являются полноценной stage/perf-lab верификацией. Численные SLA для p95/p99 должны подтверждаться отдельно.

## 3. External provider validation requires separate environment
Контуры EDO/LDAP/OIDC/enterprise интеграций в репозитории стабилизированы на уровне контрактов/readiness foundation, но production-grade проверка требует выделенного стенда и провайдерских credentials.

## 4. Restore rehearsal is still operational, not automated here
Документация по backup/restore и rollback присутствует, но полноценный scripted restore rehearsal не включен в локальный RC acceptance gate.

## 5. Frontend polish remains iterative in long-tail screens
Критичные пользовательские потоки стабилизированы, но для части административных/диагностических/аналитических экранов остается дальнейшая a11y/responsive и bundle-size оптимизация.
