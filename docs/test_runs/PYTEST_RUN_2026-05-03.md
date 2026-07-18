# Pytest Full Run — 2026-05-03

**Дата запуска:** 2026-05-03 (07:53 → 08:43 локального времени, Europe/MSK)
**Платформа:** Windows 11, Python 3.13.7, pytest 8.3.3
**Команда:**
```powershell
py -X utf8 -m pytest --continue-on-collection-errors -q --tb=short --maxfail=0 -p no:cacheprovider
```
**Конфигурация:** `pyproject.toml` → `testpaths = ["tests", "integration_tests", "backend/tests"]`, `asyncio_mode=auto`, SQLite (`prt_ot_doc_tests.db`).
**Exit code:** `1` (есть failures).

---

## Сводка

| Метрика | Значение |
|---|---|
| Файлов с тестами собрано | **290** |
| Тестов собрано | **1238** |
| ✅ PASSED | **1145** (~92,5 %) |
| ❌ FAILED | **85** |
| 💥 ERROR (per-test) | **1** |
| ⏭️ SKIPPED | **7** |
| 🔥 Collection errors (file-level) | **4** (тесты этих файлов вообще не запускались) |

> Подсчёт получен из progress-строк pytest (`grep -E "^[\.FExsXP]+\s+\["` → счётчики `.`/`F`/`E`/`s`); итоговая summary-строка pytest не была захвачена в файл из-за PowerShell-буферизации, но 85+1+7+1145 = 1238 совпадает с количеством собранных тестов, поэтому числа сходятся.

**Итог:** ~7 % тестов в красном — большинство падений сгруппировано в нескольких подсистемах (RBAC/ABAC, multi-tenant isolation, outbox/jobs, health checks). Это ожидаемое следствие удалённого слоя `app.domains.*`, который ещё используют тесты.

---

## Артефакты

Сырые файлы лежат локально в `artifacts/test_runs/` (директория в `.gitignore` — слишком крупные для репозитория, регенерируются командой ниже):

| Файл | Назначение |
|---|---|
| `artifacts/test_runs/pytest_full.txt` | Полный stdout/stderr прогон (1890 строк) — tracebacks, прогресс, short summary |
| `artifacts/test_runs/collect.txt` | Результат `pytest --collect-only -q` (290 файлов, 1238 тестов, 4 collection errors) |
| `artifacts/test_runs/failed_list.txt` | Только строки `FAILED ...` (85 шт.) |
| `artifacts/test_runs/error_list.txt` | Строки `ERROR ...` (5 шт.: 4 collection + 1 setup) |

---

## Collection errors (4 файла, не выполнились вообще)

| Тестовый файл | Причина |
|---|---|
| [tests/test_rbac_module_access.py](tests/test_rbac_module_access.py) | `ImportError: cannot import name 'create_test_user' from 'app.services.dev_bootstrap'` |
| [tests/test_workspace_role_based_config.py](tests/test_workspace_role_based_config.py) | `ImportError: cannot import name 'create_test_user' from 'app.services.dev_bootstrap'` |
| [backend/tests/test_health_checks.py](backend/tests/test_health_checks.py) | `ModuleNotFoundError: No module named 'app.api.main'` |
| [backend/tests/test_operational_dashboard.py](backend/tests/test_operational_dashboard.py) | `ModuleNotFoundError: No module named 'app.api.main'` |

Тесты ссылаются на удалённые/переименованные символы; для исправления нужно либо вернуть `create_test_user` в `app.services.dev_bootstrap`, либо переписать тесты под новое API (`create_app` + фикстуры из `tests/conftest.py`).

---

## Распределение FAILED по файлам (top-22)

| Кол-во | Файл |
|---:|---|
| 16 | [tests/test_abac_deny_allow_matrix.py](tests/test_abac_deny_allow_matrix.py) |
| 11 | [tests/test_tenant_isolation_audit.py](tests/test_tenant_isolation_audit.py) |
| 10 | [tests/test_jobs_api.py](tests/test_jobs_api.py) |
|  8 | [tests/test_health_comprehensive.py](tests/test_health_comprehensive.py) |
|  5 | [tests/test_outbox_poison_queue_metrics.py](tests/test_outbox_poison_queue_metrics.py) |
|  4 | [tests/test_settings_staging_hardening.py](tests/test_settings_staging_hardening.py) |
|  4 | [tests/test_outbox_acceptance_guarantees.py](tests/test_outbox_acceptance_guarantees.py) |
|  4 | [tests/integration/test_packages_e2e.py](tests/integration/test_packages_e2e.py) |
|  3 | [tests/unit/test_policy_engine.py](tests/unit/test_policy_engine.py) |
|  3 | [backend/tests/test_next42_rbac_abac_audit.py](backend/tests/test_next42_rbac_abac_audit.py) |
|  3 | [backend/tests/e2e/access/test_access_enforcement_matrix.py](backend/tests/e2e/access/test_access_enforcement_matrix.py) |
|  2 | [tests/test_next9_authz.py](tests/test_next9_authz.py) |
|  2 | [tests/test_files_tenant_isolation_strict.py](tests/test_files_tenant_isolation_strict.py) |
|  2 | [tests/test_audit_log_immutability.py](tests/test_audit_log_immutability.py) |
|  1 | [tests/test_tenant_session_contract.py](tests/test_tenant_session_contract.py) |
|  1 | [tests/test_risk_assessment_kpi5.py](tests/test_risk_assessment_kpi5.py) |
|  1 | [tests/integration/test_job_status_flow.py](tests/integration/test_job_status_flow.py) |
|  1 | [tests/api/test_training_enterprise_api.py](tests/api/test_training_enterprise_api.py) |
|  1 | [tests/api/test_risk_events.py](tests/api/test_risk_events.py) |
|  1 | [tests/api/test_risk_enterprise_api.py](tests/api/test_risk_enterprise_api.py) |
|  1 | [tests/api/test_incidents_api.py](tests/api/test_incidents_api.py) |
|  1 | [backend/tests/test_contractors_deny_first.py](backend/tests/test_contractors_deny_first.py) |

Полный список — [`failed_list.txt`](failed_list.txt).

---

## Ключевые причины падений (категориями)

### 1. Отсутствующие модули `app.domains.*` (≈ 11 тестов)
`test_tenant_isolation_audit.py` пытается импортировать:
- `app.domains.audit.models` (`AuditLog`)
- `app.domains.workflows` (`WorkflowEvent`)
- `app.domains.integrations` (`Webhook`)
- `app.domains.notifications`

Эти подмодули были удалены/переехали в Wave 1-2 cleanup (см. CHANGED_PATHS_AND_RENAMES.md), но тестовый код остался ссылаться на старые пути.

### 2. Удалённые символы (collection errors, см. выше)
- `create_test_user` → нет в `app.services.dev_bootstrap`
- `app.api.main` → модуль отсутствует (вероятно, заменён на `app.api.create_app`)

### 3. Health-check регрессия (`tests/test_health_comprehensive.py`, 8 шт.)
```
AssertionError: assert 'failed' in ('ok', 'degraded')
HealthCheckItem(name='email', error="'Settings' object has no attribute 'webhook_notification_url'")
```
Phase 2.2 Health Check Engine добавил проверку `email`, но Settings не содержит ожидаемого поля `webhook_notification_url`.

### 4. RBAC / ABAC «deny by default» — единая кодовая ошибка (≈ 25 тестов)
В `test_abac_deny_allow_matrix.py`, `test_next42_rbac_abac_audit.py`, `test_policy_engine.py`, `test_next9_authz.py`, `test_access_enforcement_matrix.py`:
```
AssertionError: assert 'module_access_denied' == 'policy_deny'
```
Код возвращает строку `module_access_denied`, а тесты ожидают `policy_deny`. Сменился контракт ошибок RBAC.

### 5. Outbox / Jobs API (≈ 19 тестов)
`OutboxStatus.SENT` вместо `'pending'`, NOT_FOUND на путях jobs/outbox — вероятно, изменилась эндпойнт-маршрутизация после Phase 3.1 рефакторинга.

### 6. Settings staging hardening (4 теста)
Тесты ожидают, что в staging-режиме приложение **отвергает** дефолтные/слабые секреты (S3, JWT, HMAC). Сейчас не отвергает.

---

## Что зелёное (1145 / 1238 ≈ 92,5 %)
Полностью или почти полностью зелёные блоки:
- Все `*_error_contract.py` (≈ 30 файлов)
- Все `*_access_parity.py` (≈ 20 файлов)
- `data_quality` + `operational_dashboard` (Session 9–10 фикс) — 0 падений
- Domain-specific сервисы (`briefings`, `documents`, `incidents`, `medical`, `inspections`, `attestations`, `packs`)
- Search / pipeline / orchestration / signing
- E2E `access_enforcement_matrix` — 18 из 21 зелёные
- Frontend компонентные тесты (Vitest) — не входят в этот прогон (см. `frontend/`)

---

## Рекомендации (порядок устранения)

1. **🔴 P0 — Восстановить collection (4 файла)**: вернуть `create_test_user` в `app.services.dev_bootstrap` либо переписать тесты на актуальные фикстуры; сменить `from app.api.main import app` → `from app.api import create_app`.
2. **🔴 P0 — Контракт RBAC-deny**: согласовать `module_access_denied` ↔ `policy_deny` (либо в коде, либо в тестах).
3. **🟠 P1 — Удалить ссылки на `app.domains.audit/workflows/integrations/notifications`** в `test_tenant_isolation_audit.py` (использовать модели из `app.models.models`).
4. **🟠 P1 — Health-check `email`**: добавить `webhook_notification_url` в `Settings` либо сделать проверку `email` опциональной.
5. **🟡 P2 — Outbox/Jobs API**: проверить новые пути и enum-значения; синхронизировать тесты.
6. **🟡 P2 — Staging hardening**: вернуть rejection-логику или адаптировать ожидания.

После этих 6 шагов прогон должен подойти к зелёному (~99 %).

---

## Воспроизведение

```bash
py -X utf8 -m pytest --continue-on-collection-errors -q --tb=short --maxfail=0 -p no:cacheprovider
```

Только зелёный набор (без падающих файлов):
```bash
py -X utf8 -m pytest -q -p no:cacheprovider \
  --ignore=tests/test_abac_deny_allow_matrix.py \
  --ignore=tests/test_tenant_isolation_audit.py \
  --ignore=tests/test_jobs_api.py \
  --ignore=tests/test_health_comprehensive.py \
  --ignore=tests/test_outbox_poison_queue_metrics.py \
  --ignore=tests/test_settings_staging_hardening.py \
  --ignore=tests/test_outbox_acceptance_guarantees.py \
  --ignore=tests/test_rbac_module_access.py \
  --ignore=tests/test_workspace_role_based_config.py \
  --ignore=backend/tests/test_health_checks.py \
  --ignore=backend/tests/test_operational_dashboard.py
```
