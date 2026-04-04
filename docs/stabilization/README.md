# Документация спринта стабилизации

| Документ | Назначение |
|----------|------------|
| [STABILIZATION_AUDIT.md](./STABILIZATION_AUDIT.md) | Аудит рисков и статус |
| [STABILIZATION_PLAN.md](./STABILIZATION_PLAN.md) | Этапы работ |
| [ARCHITECTURE_DECISIONS_STABILIZATION.md](./ARCHITECTURE_DECISIONS_STABILIZATION.md) | ADR |
| [REGRESSION_RISKS_AND_MITIGATIONS.md](./REGRESSION_RISKS_AND_MITIGATIONS.md) | Риски релизов |
| [TEST_COVERAGE_GAPS.md](./TEST_COVERAGE_GAPS.md) | Пробелы тестов |
| [REGRESSION_TEST_MATRIX.md](./REGRESSION_TEST_MATRIX.md) | Матрица сценариев |
| [RUNBOOK_STABILIZATION.md](./RUNBOOK_STABILIZATION.md) | Эксплуатация |
| [CONFIGURATION_HARDENING.md](./CONFIGURATION_HARDENING.md) | Конфигурация и env |

Короткая ссылка из корня репозитория: `docs/stabilization/`.

Дополнительно: корневой пакет `app/` — shim к `backend/app` (см. `CONFIGURATION_HARDENING.md`). E2E Playwright: по умолчанию ручной запуск workflow; ночной cron — в `.github/workflows/e2e-smoke.yml`.
