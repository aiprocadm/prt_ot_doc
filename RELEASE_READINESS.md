# RELEASE READINESS

## Decision

**Status:** Release Candidate — ready for demo/pilot acceptance with documented limitations.

## Why this RC is considered ready

- Критичные acceptance-сценарии сопоставлены с автотестами и smoke-командами в `ACCEPTANCE_TEST_MATRIX.md`.
- Есть единый executable gate: `make final-acceptance`.
- Контракт ошибок и OpenAPI drift покрыты отдельными проверками.
- Structured error contract стабилизирован не только на backend, но и в frontend API client/shared error states, чтобы acceptance UI не терял correlation metadata и field-level validation details.
- Tenant isolation, idempotency, async job transparency и outbox/webhook reliability подтверждаются regression-набором.
- Release evidence дополнен gap report и явным known-limitations документом.
- На frontend критичные wizard-пути больше не зависят от full page reload/disabled placeholder controls в финальном шаге: retry и handoff-навигация покрыты отдельными UI tests.

## Required verification commands

```bash
make final-acceptance
./scripts/pytest.sh tests/test_errors.py tests/e2e/final_regression/test_final_regression_api.py
./scripts/pytest.sh tests/integration/test_tenant_isolation.py tests/integration/test_job_status_flow.py
python scripts/perf/api_load.py --help
python scripts/pilot_readiness.py
```

## Demo / pilot prerequisites

- Подготовить tenant bootstrap по `docs/TENANT_BOOTSTRAP_RUNBOOK.md`.
- Использовать `X-Tenant` во всех business calls.
- Для внешних интеграций опираться на mock/stub readiness либо отдельный стенд.
- Для performance validation запускать `scripts/perf/api_load.py` против stage/postgres-backed среды, а не только локального SQLite/dev режима.

## On-prem / cloud rollout notes

- Перед rollout требуется отдельная проверка миграций и backup/restore практики в целевой среде.
- Stage/prod-specific observability, worker sizing и retry/timeout policies должны быть откалиброваны по реальной нагрузке.
- RC-документация годится как acceptance foundation, но не заменяет change-management пакет конкретного deployment.
