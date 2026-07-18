# Документация спринта стабилизации

## Канонический трекер

- **[PLAN.md](./PLAN.md)** — основной (canonical) трекер статуса, допущений, блокеров и критериев приёмки по workstream A–G.

## Рабочие документы (актуальные)

| Документ | Назначение |
|----------|------------|
| [PLAN.md](./PLAN.md) | Канонический трекер стабилизации A–G |
| [coverage.md](./coverage.md) | Текущее покрытие тестами/пайплайнами и явные пробелы |
| [restore-drill.md](./restore-drill.md) | Процедура restore-drill + артефакты доказательств |
| [perf-baseline.md](./perf-baseline.md) | Базовые perf-пробы, таблица baseline и пробелы |
| [security-gates.md](./security-gates.md) | Карта security-gates в CI/тестах |
| [rbac-matrix.md](./rbac-matrix.md) | Матрица RBAC/ABAC (endpoint × role × evidence) |
| [e2e-access.md](./e2e-access.md) | Матрица E2E-доступов/секретов и skip-риски |
| [file-hardening.md](./file-hardening.md) | Hardening-профиль для file pipeline |
| [STABILIZATION_AUDIT.md](./STABILIZATION_AUDIT.md) | Аудит рисков и статус |
| [ARCHITECTURE_DECISIONS_STABILIZATION.md](./ARCHITECTURE_DECISIONS_STABILIZATION.md) | ADR |
| [REGRESSION_RISKS_AND_MITIGATIONS.md](./REGRESSION_RISKS_AND_MITIGATIONS.md) | Риски релизов |
| [REGRESSION_TEST_MATRIX.md](./REGRESSION_TEST_MATRIX.md) | Матрица сценариев |
| [LIST_STATE_STANDARD.md](./LIST_STATE_STANDARD.md) | Стандарт Error/Loading/Empty/Table |
| [RUNBOOK_STABILIZATION.md](./RUNBOOK_STABILIZATION.md) | Эксплуатация |

## Legacy / overlap status

Следующие документы **не удаляются**, но считаются частично перекрытыми и должны обновляться только при необходимости исторического контекста:

- `STABILIZATION_PLAN.md` → **superseded by `PLAN.md`** как основной трекер статуса.
- `TEST_COVERAGE_GAPS.md` → **superseded by `coverage.md`** как текущая карта покрытий/пробелов.
- `CONFIGURATION_HARDENING.md` → частично перекрыт `security-gates.md` и `file-hardening.md` для stabilization-gates; остаётся источником по env/bootstrap.

Короткая ссылка из корня репозитория: `docs/stabilization/`.

Дополнительно: корневой пакет `app/` — shim к `backend/app` (см. `CONFIGURATION_HARDENING.md`). E2E Playwright: `frontend/e2e/smoke.spec.ts`; workflow `.github/workflows/e2e-smoke.yml`.
