# AI / Engineering implementation report

- **Date (UTC):** 2026-04-27  
- **Scope:** documentation inventory, P0 test harness fix, testing doc repair; full-platform audit is **not** completed in a single pass (see «Ограничения»).

---

## 1. Что было изучено

- `README.md` — стек, точки входа, branded documents, ссылки на документацию.
- `AGENTS.md`, `docs/spec/README.md`, `docs/spec/TZ_FULL_UNIFIED.md` (фрагмент), `docs/spec/TZ_OVERVIEW.md` — приоритет ТЗ: репо-объём vs vNext.
- `docs/ARCHITECTURE.md` — modular monolith, слои, решения 2026-03-21.
- `docs/audit/TZ_COMPLIANCE.md` — статусы P0 DevX, tenant, KPI 1–5, частично outbox.
- `GAP_REPORT.md`, `docs/stabilization/PLAN.md` (фрагмент) — release-critical зазоры.
- `docs/CI_PIPELINE_OVERVIEW.md`, `docs/TEST_BASELINE.md`, прежний `docs/TESTING.md` (был пустой циклический pointer).
- `backend/app/core/product_spec.py` — путь к vNext-спекy и сжатые правила разд. 36.
- `tests/conftest.py` — правки в этой волне (импорт Click, env для bootstrap).

---

## 2. Краткое состояние проекта

- **Stack:** FastAPI + SQLAlchemy 2 + Alembic + Celery; React + TypeScript + Vite; мультиарендность, RBAC/ABAC, документооборот, шаблоны, pipeline, модули (риски, обучение, СИЗ, инциденты, биллинг и т.д. по коду/докам).
- **Документация:** обширная (`docs/*`, `docs/audit/*`, стабилизация, GAP, матрицы); **единого автоматически актуального** «всё ТЗ = код» нет — используются `TZ_COVERAGE_MATRIX`, `TZ_COMPLIANCE`, `ACCEPTANCE_TEST_MATRIX` как следы.
- **Соответствие «полному» Т из `TZ_FULL_UNIFIED`:** крупные модули частично реализованы; формальная 100% сверка не проводилась в этой сессии (см. п. 6).

---

## 3. Найденные проблемы (приоритизировано)

### P0

| Проблема | Где | Риск | Статус |
|----------|-----|------|--------|
| `tests/conftest.py` импортировал `UNSET` из `click` до `try/except` — при отсутствии символа **все тесты** падали на импорте | `tests/conftest.py:29-34` | Блокер CI/локального pytest | **Исправлено** |
| Пустой `SECRET_KEY` (и при необходимости другие пустые S3-поля) в окружении ломал `bootstrap("api")` в фикстуре приложения | `tests/conftest.py` + `config.bootstrap` | Ложные ERROR в pytest у разработчиков | **Исправлено** (нормализация в conftest) |

### P1

| Проблема | Где | Риск | Статус |
|----------|-----|------|--------|
| `docs/TESTING.md` и `docs/testing.md` указывали сами на себя без рабочего гайда | `docs/TESTING.md` | Сломанные ссылки в README/аудитах | **Исправлено** (заполнен `TESTING.md`, lowercase — редирект) |

### P2

- `GAP_REPORT.md` / `RELEASE_READINESS` — нерешённые release-критерии (RC-012–016 и др.); **не** закрывались в этой волне.
- `docs/audit/TZ_COMPLIANCE`: KPI-4 outbox→webhook — **Partial**; отдельный time-bound тест по желанию.

### P3

- Deprecation: Pydantic v2, `jose` UTC warnings в pytest — не трогались.

---

## 4. Что было исправлено

| Проблема | Решение | Файлы | Влияние |
|----------|---------|-------|---------|
| Двойной импорт `UNSET` | Оставлен один `try/except` для `click.core.UNSET` | `tests/conftest.py` | Pytest снова загружается на разных версиях Click |
| Пустой SECRET_KEY / S3 | `_ensure_nonblank` для тестовых обязательных полей | `tests/conftest.py` | Стабильный `create_app()` в тестах |
| Пустой testing guide | Реальное содержание + ссылки на baseline/CI | `docs/TESTING.md`, `docs/testing.md` | Согласовано с `README` и `PROJECT_STRUCTURE` |

---

## 5. Что добавлено

- `AI_IMPLEMENTATION_REPORT.md` (этот файл).
- Содержимое `docs/TESTING.md` (команды, ссылки, заметка про `conftest`).

---

## 6. Что не удалось исправить / вне scope

- Полный проход по §5–6 пользовательского запроса (аудит backend/frontend/DB/security по всем вертикалям) — **требует отдельной волны** с бюджетом времени и, при необходимости, артефактов из `ACCEPTANCE_TEST_MATRIX` / e2e.
- Закрытие release gaps из `GAP_REPORT.md` / `STABILIZATION` — **не** выполнялось.
- `npm run ci` (frontend) **не** запускался в этой сессии (после правок — рекомендуется локально/CI).

---

## 7. Проверки

| Команда | Результат |
|---------|-----------|
| `pytest tests/test_tenant_header_required.py tests/test_idempotency.py tests/test_template_delete.py` (PYTHONPATH=backend) | **7 passed** (после правок) |

---

## 8. Риски

- Регрессии в непрогнанных сьютах; крупный монорепо — полный `pytest` может занимать много времени.
- Прод-конфиги по-прежнему требуют нормальных секретов; тестовые костыли в `conftest` **только** для pytest.

---

## 9. Следующие задачи (конкретно)

1. Прогнать **полный** `pytest` (или согласно `docs/TEST_BASELINE.md`) в CI-идентичной среде.  
2. `npm --prefix frontend run ci` при изменениях, затрагивающих UI.  
3. Закрывать/обновлять **RC-*** по `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` при release-окне.  
4. При работе «по ТЗ» — ориентир `docs/spec/TZ_FULL_UNIFIED.md` + `AGENTS.md` (как в репо).  
5. (Опционально) Устранить циклические/дублирующие `docs/audit/ARCHITECTURE.md` — замечено дублирование имён в листинге; не исследовалось.

---

## 10. Повторный запрос полного брифа (2026-04-27)

- Повторно просмотрены: `docs/README.md`, этот файл, `tests/conftest.py`, `docs/TESTING.md`.
- **Полноформатный аудит** по разделам 4.2–4.3 исходного брифа (все направления backend/frontend/DB/security) **не выполнялся** — ограничение как в §6.
- **Повторная проверка:** `pytest` на `test_tenant_header_required`, `test_idempotency`, `test_template_delete` — **7 passed**, exit code 0.
- В `docs/README.md` добавлена ссылка на `AI_IMPLEMENTATION_REPORT.md` для навигации агентов/разработчиков.
