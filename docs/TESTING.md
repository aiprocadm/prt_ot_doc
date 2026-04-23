# Testing Guide (Canonical)

_Last updated: 2026-04-23._

Этот документ — **канонический источник** по тестовой стратегии, локальным проверкам, CI-маппингу и merge-гейтам.

## 1. Test pyramid

Мы используем пирамиду с приоритетом быстрых и детерминированных проверок внизу и более дорогих end-to-end сценариев наверху.

| Layer | Goal | Typical scope/examples | Where runs | Merge gate |
|---|---|---|---|---|
| **Unit** | Быстрая валидация бизнес-логики и контрактов функций/сервисов | `pytest`-тесты модулей backend, `vitest` для frontend unit | Local + CI (`backend-tests`, `frontend-tests`) | **Blocking** |
| **Integration** | Проверка интеграции слоев (API, БД, tenancy/rbac, jobs/outbox) | `tests/integration/*`, `tests/api/*`, части `tests/contract/*` | Local + CI (`backend-tests`, `openapi-contract`) | **Blocking** |
| **E2E / Acceptance** | Сквозные пользовательские/доменные сценарии и регрессионные срезы | Сценарии из `ACCEPTANCE_TEST_MATRIX.md`, `make final-acceptance` | Local (pre-PR / RC) + selective CI | **Blocking only for mapped CI jobs** |
| **Performance** | Smoke-гарантии latency/error-rate/throughput для ключевых endpoint-ов | `scripts/perf/api_load.py` профили | CI (`perf-smoke`) + RC локально | **Blocking in CI (`perf-smoke`)** |
| **Security** | SAST, secret/vuln scanning, policy checks | `bandit`, `gitleaks`, `trivy`, security exceptions validation | CI (`security-*`, `secret-scan`, `sast-*`, `container-image-scan`) | **Blocking** |

### Принцип применения
- Любое изменение должно иметь минимум **unit/integration** покрытие на затронутом участке.
- Для изменений пользовательских потоков/контрактов обязательно проверять **acceptance slices** (см. `ACCEPTANCE_TEST_MATRIX.md`).
- Для high-risk изменений перед релиз-кандидатом добавляются **perf + security + smoke-compose** проверки.

## 2. Mandatory local commands

Минимальный обязательный локальный набор перед PR:

```bash
# Backend core
./scripts/pytest.sh tests/test_entrypoints.py
./scripts/pytest.sh tests/test_errors.py

# Frontend quality gates
npm --prefix frontend run typecheck
npm --prefix frontend run test

# Contract sanity
./scripts/pytest.sh tests/contract/test_openapi_contract.py
```

Если изменялись шаблоны/документогенерация/брендинг, дополнительно:

```bash
./scripts/pytest.sh tests/test_documents_generate.py tests/test_template_catalog_scope.py
PYTHONPATH=backend python scripts/contract/validate.py
```

Если изменялись tenancy/rbac/outbox/jobs:

```bash
./scripts/pytest.sh \
  tests/integration/test_tenant_isolation.py \
  tests/integration/test_abac_query_isolation.py \
  tests/integration/test_job_status_flow.py
```

## 3. CI job mapping

Ниже отображено, что запускается в CI и какие jobs блокируют merge.

| CI job (`.github/workflows/ci.yml`) | Pyramid layer | What runs | Blocks merge |
|---|---|---|---|
| `security-exceptions` | Security | `check_security_exceptions.py` | Yes |
| `lint-and-static` | Unit/static | Scoped query/runtime/default-secret/static gates | Yes |
| `dependency-vulnerability-scan` | Security | Trivy FS vulnerability gate | Yes |
| `secret-scan` | Security | Gitleaks | Yes |
| `sast-static-analysis` | Security | Bandit high/high | Yes |
| `container-image-scan` | Security | Trivy image scan | Yes |
| `sbom-generation` | Security/compliance evidence | SBOM artifact generation | Yes |
| `alembic-postgres-upgrade` | Integration | Postgres migration upgrade/idempotency | Yes |
| `backend-tests` | Unit + Integration | Full backend pytest + coverage baseline gate | Yes |
| `openapi-contract` | Integration/contract | Contract-marked tests | Yes |
| `frontend-tests` | Unit + Integration | frontend CI + critical coverage gate | Yes |
| `smoke-compose` | E2E smoke | docker compose + `make smoke` | Yes |
| `perf-smoke` | Performance | deterministic perf profiles | Yes |

Дополнительно есть отдельный workflow `.github/workflows/e2e-smoke.yml` для Playwright smoke-срезов (mandatory + credential flows). Для backend bootstrap в нём зафиксирован `actions/setup-python` с версией **3.12** (выровнено с `pyproject.toml` и основным CI).

## 4. Cross-links: acceptance and coverage gates

### Acceptance matrix
- Матрица сценариев и точечных evidence/команд: `ACCEPTANCE_TEST_MATRIX.md`.
- Там фиксируется **что именно подтверждает сценарий**, а этот гайд фиксирует **когда и в каком контуре запускать**.

### Stabilization coverage
- Политика backend coverage и baseline-гейт: `docs/stabilization/coverage.md`.
- Merge блокируется, если `backend-tests` падает на `check_backend_coverage_baseline.py`.

### Что блокирует merge
- Любой failing CI job из таблицы выше блокирует merge.
- Отдельно критичны:
  - contract regressions (`openapi-contract`),
  - backend coverage regression (`backend-tests` + baseline check),
  - security gates (`secret-scan`, Trivy, Bandit).

## 5. Minimal pre-PR checks

Минимум, который должен пройти разработчик перед открытием PR:

```bash
# 1) Быстрый backend sanity
./scripts/pytest.sh tests/test_entrypoints.py tests/test_errors.py

# 2) Frontend quality
npm --prefix frontend run typecheck
npm --prefix frontend run test

# 3) Contract gate
./scripts/pytest.sh tests/contract/test_openapi_contract.py

# 4) Optional but recommended for infra-sensitive changes
python scripts/ci/check_scoped_queries.py
python scripts/ci/check_default_secrets.py
```

## 6. Release candidate checks

Полный набор для release candidate (до финального go/no-go):

```bash
# Acceptance bundle
make final-acceptance

# Full local CI approximation
make ci-local

# Smoke in compose env
./scripts/smoke.sh

# Perf deterministic smoke
python scripts/perf/api_load.py --help

# Coverage baseline check (после прогона pytest с coverage)
python scripts/ci/check_backend_coverage_baseline.py \
  --coverage-json artifacts/coverage.json \
  --baseline docs/stabilization/backend_coverage_baseline.json
```

Дополнительно для RC рекомендуется сверяться с:
- `docs/RUNBOOK_RC.md`
- `docs/RELEASE_READINESS.md`
- `docs/KNOWN_LIMITATIONS_RC.md`

## 7. Files API compatibility boundary checks

Для файлового API действует жесткая граница совместимости:

- **Канонический слой поведения:** только `backend/app/modules/files/api.py` (маршрут `/api/v1/files/*`).
- **Legacy-слой:** только `backend/app/api/routes/files.py`, публикуется под `/api/v1/files-legacy/*` и только при `ENABLE_FILES_LEGACY_ROUTES=true`.

Обязательные регрессионные проверки:

```bash
# Проверка переключения legacy-router через feature-flag
./scripts/pytest.sh tests/test_route_group_registry.py -k files_router_registration_switches_with_legacy_flag

# Проверка parity по authz/tenant-контракту между canonical и legacy routes
./scripts/pytest.sh tests/test_files_access_parity.py -k legacy_upload_and_download_dependencies_match_canonical_tenant_and_abac_contract
```


## 8. Release-critical traceability and priority order

Для стабилизации релиз-критичного контура используем фиксированный приоритет покрытия:

1. `auth/session`
2. `rbac_abac`
3. `files`
4. `tenant isolation`
5. `document orchestration`
6. `landing/protected routes`

Канонический mapping user paths → tests → workflow jobs → artifacts ведётся в `docs/stabilization/acceptance-traceability.md`.

## 9. E2E smoke credential-independence policy

`e2e-smoke` должен оставаться запускаемым без внешних секретов:

- mandatory baseline: `playwright-smoke-minimal` (`mandatory (no external creds)`),
- credential flows: `playwright-smoke-credential` c матрицей `bootstrap_local` + `repo_secrets`.

Ветка `bootstrap_local` является обязательной release-базой и не требует внешних credential/secrets; `repo_secrets` — дополнительный канал при наличии секретов в репозитории.
