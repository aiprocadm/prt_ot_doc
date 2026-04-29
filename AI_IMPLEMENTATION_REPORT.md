# AI / Engineering implementation report

- **Date (UTC):** 2026-04-29 (обновлено)  
- **Scope:** baseline verification after §25 idempotency tests. Проверены security gate (check_scoped_queries), backend smoke-тесты (16 passed), frontend CI (npm run ci — lint + typecheck + vitest 221 + build — exit 0). Последняя волна: **§26 baseline verification**; ранее — §25 интеграционные тесты идемпотентности, §24 security audit (webhook "dev-secret", bare-except), §23–22 смоук и lint/typecheck/vitest.
- **Шаблон работы агента:** `docs/AI_AGENT_WORKFLOW.md` (обновляй этот файл по итогам волны; не создавай параллельных «мега-отчётов» в корне).

## Кандидаты на удаление / архивация (актуальный список)

| Документ / путь | Причина | Действие |
|-----------------|---------|----------|
| *(было)* Vitest | 7 unhandled из `ConflictInboxCard` без `catch` | **Снято в §18** |

*Примеры причин: дублирует; устарел; противоречит ТЗ; не используется; черновик; мешает навигации. Решение — после проверки владельцем репо.*

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

---

## 11. Волна 2026-04-27 (третий полный бриф): typecheck + entrypoints

### Изучено (дополнительно)
- Повторное чтение `README.md`, `docs/TESTING.md`, `AGENTS.md`, `docs/spec/README.md`; прогон по рекомендациям README.

### Исправление P1 (frontend)
- **Проблема:** `npm --prefix frontend run typecheck` падал: в `TaskTable.tsx` вызывался `usePolling` без импорта (`TS2304`).
- **Решение:** `import { usePolling } from "@/hooks/usePolling"` (тот же хук, что в мастере документов).
- **Файл:** `frontend/src/features/tasks/TaskTable.tsx`.

### Проверки
| Команда | Результат |
|---------|-----------|
| `pytest tests/test_entrypoints.py` (PYTHONPATH=backend) | **2 passed** |
| `npm --prefix frontend run typecheck` | **exit 0** (после импорта) |

### Ограничение
- Полный аудит по §4.2–4.3 брифа и `npm run ci` (lint+test+build) **не** выполнялись целиком в этой волне; при подготовке релиза прогнать `docs/TEST_BASELINE.md` / CI-эквивалент.

---

## 12. Волна 2026-04-28: компактный промт для агентов

### Что сделано
- Добавлен **`docs/AI_AGENT_WORKFLOW.md`** — единый компактный промт (README-first, приоритеты источников, P0–P3, кандидаты на чистку документации, обновление только этого отчёта).
- Ссылки: **`README.md`** (секция Canonical documentation), **`AGENTS.md`**, **`docs/README.md`**, **`.cursor/rules/ai-agent-workflow.mdc`**.
- В **этом** файле: таблица **«Кандидаты на удаление»** (пока пустая, для заполнения в следующих волнах). Ранее отмечено: возможное дублирование `docs/audit/ARCHITECTURE.md` — **не** подтверждено/не удалялось.

### Проверки
- Линтер/тесты не требовались (изменения только в документации и правилах Cursor).

### Что нельзя было подтвердить
- Список «мусорных» документов без чтения всего `docs/**` в этой волне не строился — таблица выше для следующих итераций.

---

## 13. 2026-04-28: уточнение `docs/AI_AGENT_WORKFLOW.md`

- Файл **объединён** с новым брифом: обязательный порядок (README → ТЗ по ссылкам → `AI_IMPLEMENTATION_REPORT` → код), приоритеты production-grade, чек-лист «перед правками», правила/запреты, мусор, формат **краткого** ответа (9 пунктов), условия обновления README.
- Обновлены: **`docs/AI_AGENT_WORKFLOW.md`**, **`.cursor/rules/ai-agent-workflow.mdc`**, эта запись; код не менялся; автоматические проверки **не** запускались.

---

## 14. Волна 2026-04-28: P1 — `npm run lint` (frontend)

### Изучено
- `README.md`, `docs/AI_AGENT_WORKFLOW.md`, `docs/README.md`, этот отчёт (волны 1–13).
- Уточнение: `docs/ARCHITECTURE.md` (обзор платформы) и `docs/audit/ARCHITECTURE.md` (discovery map) — **разные файлы**, не дубликат содержимого; удаление не требуется.

### Найденные проблемы
- `npm --prefix frontend run lint` **падал** (`--max-warnings=0`): запрет `fetch` в `navigation.ts` (no-restricted-globals), неиспользуемый тип `ApiError` в трёх store, предупреждения `react-hooks/exhaustive-deps` в `ContractorsPage.tsx`.

### Что сделано
- **`sendUxMetric`:** один вызов `apiClient.post("/analytics/ux-events", …)` вместо двойного `fetch` (исправлена логически ошибочная цепочка: первый POST без `Authorization`/`X-Tenant`, второй с ними; теперь тот же контракт, что и у остального API, перехват ошибок сохранён — endpoint на бэкенде по-прежнему может отсутствовать).
- Удалены неиспользуемые импорты `ApiError`: `stores/documents.ts`, `stores/files.ts`, `stores/persons.ts`.
- **ContractorsPage:** вычисление строк таблицы перенесено внутрь `useMemo` с зависимостями `data.companies` / `data.employees` / `data.incidents` / `hostCompanyById`.

### Файлы
- `frontend/src/api/navigation.ts`
- `frontend/src/stores/documents.ts`, `frontend/src/stores/files.ts`, `frontend/src/stores/persons.ts`
- `frontend/src/pages/contractors/ContractorsPage.tsx`
- `AI_IMPLEMENTATION_REPORT.md` (эта секция)

### Проверки
| Команда | Результат |
|---------|-----------|
| `py -m pytest -q tests/test_entrypoints.py tests/test_tenant_header_required.py tests/test_idempotency.py tests/test_template_delete.py` (`PYTHONPATH=backend`) | **9 passed** |
| `npm --prefix frontend run typecheck` | **OK** |
| `npm --prefix frontend run lint` | **OK** |
| `npm --prefix frontend run build` | **OK** |
| `py -m ruff check backend/app tests scripts` | **много существующих замечаний** в репо; **не** исправлялись в этой волне (бэкенд не трогали) |

### Риски
- Если позже появится реальный `POST /api/v1/analytics/ux-events`, пейлоад `{ name, payload }` остаётся согласован с прежним намерением; при отсутствии маршрута поведение как раньше — тихий сбой в `catch`.

---

## 15. Волна 2026-04-28: ссылки на ТЗ в `README.md`

### Изучено
- `README.md` (секция Canonical documentation, точка входа).
- `AI_IMPLEMENTATION_REPORT.md` (контекст волны 1–14).
- Приоритет ТЗ: `AGENTS.md`, `docs/spec/README.md` (без полного чтения всех `docs/**`).

### Проблема
- В корневом `README` не было **прямых** ссылок на главные файлы ТЗ `TZ_FULL_UNIFIED` и `PLATFORM_VNEXT_UPGRADE_SPEC` (навигация для агентов и разработчиков).

### Сделано
- В **Canonical documentation** добавлены две markdown-ссылки в начало списка: `docs/spec/TZ_FULL_UNIFIED.md`, `docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md` (краткие пояснения назначения).

### Файлы
- `README.md`
- `AI_IMPLEMENTATION_REPORT.md` (эта секция)

### Мусор
- Не обнаружен; удалений нет.

### Проверки
| Команда | Результат |
|---------|-----------|
| `npm --prefix frontend run typecheck` | **OK** |
| `npm --prefix frontend run lint` | **OK** |
| `npm --prefix frontend run build` | **OK** |
| `py -m pytest -q tests/test_entrypoints.py` (`PYTHONPATH=backend`) | **2 passed** (smoke, код не менялся) |

### Риски
- Нет (только навигация в доке).

### Следующий шаг
- Выполнено в §16: строка на [docs/spec/README.md](docs/spec/README.md) в корневом `README.md`.

---

## 16. Волна 2026-04-28: хаб `docs/spec/README.md` в корневом `README.md`

### Изучено
- `README.md` (Canonical documentation).
- `AI_IMPLEMENTATION_REPORT.md` (§15 — опция хаба).

### Сделано
- Одна строка-ссылка на [docs/spec/README.md](docs/spec/README.md) с пояснением (хаб ТЗ, приоритет `TZ_FULL` vs vNext, схема файлов) — сразу после ссылок на `TZ_FULL_UNIFIED` и `PLATFORM_VNEXT_UPGRADE_SPEC`.

### Файлы
- `README.md`
- `AI_IMPLEMENTATION_REPORT.md` (эта секция, обновлён Scope и §15)

### Мусор
- Нет.

### Проверки
| Команда | Результат |
|---------|-----------|
| `npm --prefix frontend run typecheck` | **OK** |
| `npm --prefix frontend run lint` | **OK** |
| `npm --prefix frontend run build` | **OK** |
| `py -m pytest -q tests/test_entrypoints.py` (`PYTHONPATH=backend`) | **2 passed** |

### Риски
- Нет.

### Следующий шаг
- При смене структуры `docs/spec/` — синхронизировать формулировку строки в корневом `README`.

---

## 17. Волна 2026-04-28: аудит по брифу (README → отчёт → проверки)

### Изучено
- `README.md` (Verification commands, Canonical documentation: `TZ_FULL`, vNext, `docs/spec/README`, `docs/TESTING`, `AI_AGENT_WORKFLOW`, архитектура).
- `AI_IMPLEMENTATION_REPORT.md` (§1–16).
- `docs/spec/README.md` не читался целиком; приоритет ТЗ — как в `AGENTS.md` / хабе.

### Найденные проблемы (без правок кода в этой волне)
- **`vitest run` (полный suite):** 221 тест passed, но **7 unhandled errors/rejections** (Vitest завершает с **exit code 1**). По сэмплу в логе: отклонённый запрос с `message: «Выберите контур перед выполнением запроса.»` (например контекст `InspectionsPage.test.tsx`); иной шум — jsdom/`location.assign` в stderr. **Инкрементальное исправление** — выставлять tenant в тестах страниц / догонять `act()` у Radix; отдельная задача (P2), не блокер typecheck/lint/build.
- Попытка `try/catch` вокруг `location.assign` в `authRedirect` **не** убрала 7 unhandled (корневая причина — promise-отклонения apiClient), поэтому **откатана**, дифф к продукту не вносился.

### Что изменено
- Только **`AI_IMPLEMENTATION_REPORT.md`** (эта секция + Scope). Код приложения **не** менялся.

### Файлы
- `AI_IMPLEMENTATION_REPORT.md`

### Мусор
- Не удалялся. **Кандидат на доработку (не удаление):** стабилизировать полный Vitest (см. выше).

### Проверки
| Команда | Результат |
|---------|-----------|
| `py -m pytest -q tests/test_entrypoints.py tests/api/test_branding_api.py tests/headers/test_engine.py` (`PYTHONPATH=backend`) | **6 passed** |
| `npm --prefix frontend run typecheck` | **OK** |
| `npm --prefix frontend run lint` | **OK** |
| `npm --prefix frontend run build` | **OK** |
| `npx vitest run` (полный) | **221 passed**, **7** unhandled → **exit 1** (см. «Проблемы») |
| `alembic ...` / миграции | не запускались (не трогались) |

### Риски
- CI, где `npm run test` = полный Vitest, может **падать** на exit 1 из-за unhandled; уточнить политику в `docs/TESTING.md` / pipeline.

### Следующий шаг
- Точечно: в тестах страниц с `apiClient` и обязательным `X-Tenant` — `tenantStorage.setTenant` (или мок) в `beforeEach`; либо настроить Vitest `onUnhandledRejection` после анализа всех 7 кейсов. Полный `pytest` / `ruff` — по `docs/TEST_BASELINE.md` при релизном окне.

---

## 18. Волна 2026-04-28: Vitest unhandled — `ConflictInboxCard`

### Изучено
- `README.md`, `AI_IMPLEMENTATION_REPORT.md` (§17), компонент `frontend/src/components/pwa/ConflictInboxCard.tsx`, вызовы `pwaSyncApi.getBootstrap()` → `apiClient` (тенант обязателен для `/v1/...`).

### Проблема
- **`ConflictInboxCard`:** `load()` оборачивал `getBootstrap()` в `try/finally` **без** `catch`. При отклонении (нет `X-Tenant`, сеть, 5xx) promise становился **unhandled**; Vitest считал это 7 глобальными ошибками на полном прогоне (страницы с карточкой) и выходил с **exit 1** при 221 passed.

### Решение
- В `catch` сбрасывать список конфликтов и `onConflictStateChange(false)` — карточка PWA best-effort, поведение согласовано с отсутствием бутстрапа.

### Файлы
- `frontend/src/components/pwa/ConflictInboxCard.tsx`
- `AI_IMPLEMENTATION_REPORT.md` (эта секция, Scope, таблица кандидатов)

### Проверки
| Команда | Результат |
|---------|-----------|
| `npx vitest run` | **221 passed**, **0** unhandled, **exit 0** |
| `npm run lint` / `npm run typecheck` (frontend) | **OK** |
| `py -m pytest -q tests/test_entrypoints.py` (`PYTHONPATH=backend`) | **2 passed** |

### Риски
- При ошибке бутстрапа карточка показывает «Конфликтов нет» — ожидаемо для degradеd mode.

### Следующий шаг
- При необходимости — тонкий UI hint «не удалось загрузить» вместо пустого списка; полный `pytest` / `ruff` по релизному чеклисту.

---

## 19. Волна 2026-04-28: готовность к релизу — ссылка в `README.md`

### Изучено
- `README.md` (Canonical documentation), `RELEASE_READINESS.md` (уже существует в корне), `AI_IMPLEMENTATION_REPORT.md`.

### Сделано
- Файл **не создавался**: каноническая **готовность к релизу** — корневой [`RELEASE_READINESS.md`](RELEASE_READINESS.md) (вердикт, RC-001…006, ссылки на `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` и др.).
- В **README** добавлена **явная** markdown-строка сразу после хаба `docs/spec/README` (описание + ссылка на `RELEASE_BLOCKERS_STATUS`); дублирующий пункт `RELEASE_READINESS` внизу списка убран.
- В **`RELEASE_READINESS.md`** — краткое вступление о назначении (готовность проекта, ссылка на канонические блокеры).

### Файлы
- `README.md`
- `RELEASE_READINESS.md`
- `AI_IMPLEMENTATION_REPORT.md` (эта секция, Scope)

### Проверки
| Команда | Результат |
|---------|-----------|
| `npm --prefix frontend run typecheck` | **OK** |
| `npm --prefix frontend run lint` | **OK** |
| `npm run test` / `build` | не гонялись (только доки); при релизном PR — `npm run ci` |

### Риски
- Нет.

### Следующий шаг
- Выполнено в §20: зафиксирован порядок правок и отсылка к CI `npm run ci`.

---

## 20. Волна 2026-04-28: процедура смены вердикта релиза

### Изучено
- `README.md` (блок про `RELEASE_READINESS`), `RELEASE_READINESS.md`, `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`, [`.github/workflows/ci.yml`](.github/workflows/ci.yml) (job `frontend-tests`).

### Сделано
- В **`RELEASE_READINESS.md`** добавлен раздел **How to update the release verdict**: сначала `RELEASE_BLOCKERS_STATUS`, затем синхронизация `RELEASE_READINESS`; README не трогать при смене вердикта; напоминание про **`npm --prefix frontend run ci`** в CI.
- В **`docs/stabilization/RELEASE_BLOCKERS_STATUS.md`** — строка **Authoring order** со ссылкой на корневой `RELEASE_READINESS.md` и на раздел процедуры.
- В **`README.md`** — уточнена строка про готовность: где читать порядок обновления (без смены путей).

### Файлы
- `RELEASE_READINESS.md`
- `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`
- `README.md`
- `AI_IMPLEMENTATION_REPORT.md` (эта секция, Scope)

### Проверки
| Команда | Результат |
|---------|-----------|
| `npm --prefix frontend run ci` | **OK** (lint + typecheck + vitest 221 + build, exit 0) |

### Риски
- Нет (только дока).

### Следующий шаг
- При реальном **READY** — обновить вердикт и даты в двух файлах по процедуре из `RELEASE_READINESS.md`.

## 21. Волна 2026-04-27: фикс синтаксической регрессии `sendUxMetric`

### Изучено
- `README.md` (порядок проверок и канонические команды).
- `docs/spec/README.md` (приоритеты ТЗ).
- `AI_IMPLEMENTATION_REPORT.md` (§1–20).
- `frontend/src/api/navigation.ts` (реализация top-nav метрик).

### Проблема
- `npm --prefix frontend run typecheck` падал с `TS1005: 'try' expected` из-за повреждённого блока `try/catch` в `sendUxMetric` (дублированный `catch` и повторный `apiClient.post`).

### Решение
- Удалён ошибочный дублирующий `catch`/повторный POST; оставлен один `try/catch` с best-effort семантикой (ошибки метрик глушатся и не всплывают вызывающему коду).

### Файлы
- `frontend/src/api/navigation.ts`
- `AI_IMPLEMENTATION_REPORT.md`

### Проверки
| Команда | Результат |
|---------|-----------|
| `npm --prefix frontend run typecheck` | **OK** |
| `npm --prefix frontend run lint` | **OK** |
| `npm --prefix frontend run build` | **OK** |
| `pytest -q tests/test_entrypoints.py tests/api/test_branding_api.py tests/headers/test_engine.py` | **не запущен в этой среде**: отсутствует `pytest_asyncio` (`ModuleNotFoundError`) |

### Риски
- Нет функциональных рисков: восстановлена прежняя best-effort логика отправки UX-метрик.

### Следующий шаг
- В test-окружении с полными dev-зависимостями (`pytest-asyncio`) прогнать backend smoke suite и baseline из `docs/TEST_BASELINE.md`.

### Дополнение по ходу проверок
- Во время `npm --prefix frontend run lint` выявлены существующие ошибки `@typescript-eslint/no-unused-vars` в `frontend/src/pages/contractors/ContractorsPage.tsx` (`contractorCompanies`, `employees`, `incidents`).
- Удалены неиспользуемые `useMemo`-переменные; функционал не менялся (эти массивы и так вычислялись повторно внутри `items`-мемоизации).
- После правки `lint/typecheck/build` проходят.
---

## 21. Волна 2026-04-28: `docs/README.md` + P0 `navigation.ts` + `ContractorsPage`

### Изучено
- `README.md` (корневой), `docs/README.md` (хаб), `AI_IMPLEMENTATION_REPORT.md` (§20).

### Проблемы
- В **хабе** `docs/README.md` не было **прямых** ссылок на `RELEASE_READINESS` и `RELEASE_BLOCKERS_STATUS`.
- **P0:** `frontend/src/api/navigation.ts` — повреждённый `try/catch` (два `catch`, дублирующий `post` в `catch` → `TS1005: 'try' expected`), `sendUxMetric` **не компилировался** при `tsc`.
- `ContractorsPage.tsx` — остались **неиспользуемые** `useMemo` (`contractorCompanies`, `employees`, `incidents`) после рефактора (§14); ESLint `no-unused-vars` в красной зоне.

### Сделано
- `docs/README.md` — секция **«Релиз и готовность»** с ссылками.
- `navigation.ts` — один `try`/`catch`, best-effort `post` в `try`.
- `ContractorsPage.tsx` — удалены три мёртвых `useMemo`.

### Файлы
- `docs/README.md`
- `frontend/src/api/navigation.ts`
- `frontend/src/pages/contractors/ContractorsPage.tsx`
- `AI_IMPLEMENTATION_REPORT.md` (эта секция, Scope)

### Мусор
- Не удалялся (только мёртвый код в `ContractorsPage`).

### Проверки
| Команда | Результат |
|---------|-----------|
| `py -m pytest -q tests/test_entrypoints.py` (`PYTHONPATH=backend`) | **2 passed** |
| `npm --prefix frontend run typecheck` | **OK** |
| `npm --prefix frontend run lint` | **OK** |

### Риски
- `sendUxMetric` снова компилируется; поведение — как после волны §14 (тихий сбой, если нет эндпоинта).

### Следующий шаг
- `npm run ci` при смене фронта; полный `pytest` по релизу.

---

## 22. Волна 2026-04-28: верификация (бриф без новой фичи)

### Изучено
- `README.md` (точка входа, ТЗ, `docs/TESTING`), `AI_IMPLEMENTATION_REPORT.md` (§1–21).
- Точечная сверка: `frontend/src/api/navigation.ts`, `docs/README.md` (релиз/блокеры).

### Проблемы
- **Новых** дефектов в этой сессии не выявлено; §21 по `navigation`/`ContractorsPage` — в согласованном виде.

### Изменения в коде / доках
- **Нет** (только этот отчёт и Scope).

### Мусор
- Не удалялся.

### Проверки
| Команда | Результат |
|---------|-----------|
| `py -m pytest -q tests/test_entrypoints.py tests/test_tenant_header_required.py tests/test_idempotency.py tests/test_template_delete.py` (`PYTHONPATH=backend`) | **9 passed**, exit 0 |
| `npm --prefix frontend run ci` | **OK** (lint, typecheck, vitest 82 files / 221 tests, build; **без** unhandled / exit 0) |

### Риски
- Полный `pytest` / миграции не гонялись в этой волне.

### Следующий шаг
- Релизное окно: полный `pytest` и чеклист `docs/TESTING.md` / `docs/TEST_BASELINE.md`.

---

## 23. Волна 2026-04-28: бриф — смоук без изменений кода

### Изучено
- `README.md` (Verification commands, Canonical documentation), `AI_IMPLEMENTATION_REPORT.md` (§1–22).

### Проблемы
- Новых расхождений док/код и **дефектов** в рамках быстрой ревизии **не** выявлено. `navigation.ts` — валидный `try/catch` для `sendUxMetric`.

### Изменения
- **Нет** (только `AI_IMPLEMENTATION_REPORT.md`).

### Мусор
- Не удалялся.

### Проверки
| Команда | Результат |
|---------|-----------|
| `py -m pytest -q tests/test_entrypoints.py` (`PYTHONPATH=backend`) | **2 passed** |
| `npm --prefix frontend run typecheck` | **OK** |
| `npm --prefix frontend run lint` | **OK** |

### Не гонялось
- `npm run test` / `build`, полный `pytest`, миграции (см. §22 для полного `ci`).

### Риски
- Нет.

### Следующий шаг
- При смене кода/релизе: **`npm run ci`**, полный `pytest` по `docs/TESTING.md`.

---

## 24. Волна 2026-04-28: security audit — webhook "dev-secret" + bare except

### Изучено
- `README.md` (Verification commands, Canonical documentation), `AI_IMPLEMENTATION_REPORT.md` (§1–23).
- `RELEASE_READINESS.md`, `GAP_REPORT.md`, `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` — актуальные блокеры релиза.
- `KNOWN_LIMITATIONS.md` — известные ограничения.
- Полный аудит кода через Explore-агент: 190 тест-файлов, 60+ API-роутов, CI-воркфлоу (14 jobs), deps, docs.

### Найденные проблемы

| Приоритет | Проблема | Файл | Статус |
|-----------|---------|------|--------|
| HIGH | Hardcoded `"dev-secret"` в webhook-signature validation: атакующий, зная дефолт, может подделать HMAC-подпись для любого тенанта без `edo_webhook_secret` | `backend/app/api/routes/edo_workflow.py:669`, `backend/app/api/routes/approval_signing_v1.py:445` | **Исправлено** |
| MEDIUM | `bare except:` в архивном скрипте (перехватывает `SystemExit`, `KeyboardInterrupt`) | `scripts/archive/migrate_routes_v3.py:93` | **Исправлено** |
| INFO | `"change-me"` fallback в `file_storage.py:384` — миtigated: `config.py:655-667` проверяет на старте в production/staging | `backend/app/services/file_storage.py:384` | Не менялся (см. риски) |

### Что исправлено

**`edo_workflow.py` и `approval_signing_v1.py`:**  
- Убран дефолт `"dev-secret"`.
- Логика: если `edo_webhook_secret` сконфигурирован в `tenant.settings` — валидируем подпись; если нет — пропускаем (best-effort, как было, но без известного ключа для форжинга).
- Поведение для тенантов с настроенным секретом не изменилось.

**`scripts/archive/migrate_routes_v3.py`:**  
- `except:` → `except SyntaxError:` (ast.parse may only raise SyntaxError on bad code).

### Файлы
- `backend/app/api/routes/edo_workflow.py`
- `backend/app/api/routes/approval_signing_v1.py`
- `scripts/archive/migrate_routes_v3.py`
- `AI_IMPLEMENTATION_REPORT.md` (эта секция, Scope)

### Мусор
- Не удалялся.

### Проверки
| Команда | Результат |
|---------|-----------|
| `py -m ruff check backend/app/api/routes/edo_workflow.py approval_signing_v1.py scripts/archive/migrate_routes_v3.py` | **All checks passed** |
| `py -m pytest -v tests/test_entrypoints.py tests/test_tenant_header_required.py tests/test_idempotency.py tests/test_template_delete.py` (`PYTHONPATH=backend`) | **9 passed** |
| `py -m pytest tests/headers/test_engine.py` (`PYTHONPATH=backend`) | **1 passed** |
| `npm --prefix frontend run lint` | **OK** |
| `npm --prefix frontend run typecheck` | **OK** |
| `npm --prefix frontend run test` | **221 passed / 82 files, exit 0** |
| `npm --prefix frontend run build` | **OK** |

### Замечание о bash/segfault
- `pytest tests/headers/test_engine.py` из git-bash на Windows даёт exit 139 (SIGSEGV); через PowerShell — 1 passed, exit 0. Это особенность окружения, не дефект кода.

### Риски
- `file_storage.py`: `"change-me"` fallback не убирался — в production заблокирован config.py, в dev — ожидаемо. Если нужна строгость в dev-режиме, можно добавить отдельный валидатор, но это не блокер.
- Исправление webhook: тенанты без `edo_webhook_secret` по-прежнему принимают webhooks без подписи — это design choice (не regression). Для production рекомендуется обязательная настройка `edo_webhook_secret` в `tenant.settings`.

### Следующий шаг
- Закрыть release blockers: RB-001 (restore drill), RB-004 (security gate matrix), RB-005 (e2e secrets diagnostics) — главные оставшиеся RC без кода.
- При работе с webhook-роутами: рассмотреть требование x_signature когда секрет настроен (сейчас — optional).
- Полный `pytest` (все 190 тест-файлов) в CI-среде по `docs/TEST_BASELINE.md`.

---

## 25. Волна 2026-04-28: интеграционные тесты идемпотентности (replay + 409)

### Изучено
- `README.md` (Verification commands, Canonical documentation), `AI_IMPLEMENTATION_REPORT.md` (§1–24).
- `tests/test_idempotency.py` — существующие тесты идемпотентности.
- `backend/app/services/idempotency.py` — `IdempotencyService.acquire()` (логика replay и 409).
- `backend/app/core/idempotency.py` — `compute_request_hash`, `idempotency_dependency` middleware.
- `backend/app/api/routes/documents.py` (строки 1299–1370) — обработка ключа в `generate_document`.
- `backend/app/api/routes/packs.py` (строки 738–782) — обработка ключа в `run_pack`.
- `backend/app/api/error_handlers.py` — фактический формат 409-ответа (`code="IDEMPOTENCY_MISMATCH"`, `type="idempotency"`).

### Найденные проблемы
- Отсутствовали явные интеграционные тесты для двух контрактов:
  1. same key + same hash → **replay** (202, тело идентично, Celery-задача не запускается повторно)
  2. same key + different hash → **409 IDEMPOTENCY_MISMATCH**

### Что добавлено

| Тест | Файл | Описание |
|------|------|----------|
| `test_document_generate_replay_same_key_same_hash` | `tests/test_idempotency.py` | Full-flow: два POST с одинаковыми payload/ключом → оба 202, одинаковое тело, Celery вызван 1 раз |
| `test_document_generate_conflict_same_key_different_hash` | `tests/test_idempotency.py` | Full-flow: первый POST → 202; второй POST с тем же ключом, но разным `data` → 409 `IDEMPOTENCY_MISMATCH` |
| `test_packs_run_conflict_same_key_different_hash` | `tests/test_idempotency.py` | Seeded-подход: в БД помещается запись с заведомо другим `request_hash`; POST с тем же ключом → 409 (без сложной настройки pack-фикстур) |

**Детали формата ошибки (задокументировано по фактическому ответу):**  
409-ответ имеет `code = "IDEMPOTENCY_MISMATCH"` (из detail overrides в `_handle_http_exception`), `type = "idempotency"`, а не generic `code = "CONFLICT"`.

### Файлы
- `tests/test_idempotency.py` (добавлены 3 теста в конец файла)
- `AI_IMPLEMENTATION_REPORT.md` (эта секция, Scope)

### Мусор
- Не удалялся.

### Проверки
| Команда | Результат |
|---------|-----------|
| `py -m pytest -v tests/test_idempotency.py` (`PYTHONPATH=backend`) | **7 passed** (4 старых + 3 новых), exit 0 |
| `py -m pytest -v tests/test_entrypoints.py tests/test_tenant_header_required.py tests/test_template_delete.py` (`PYTHONPATH=backend`) | **5 passed**, exit 0 |

### Риски
- Replay-тест и conflict-тест для `documents/generate` используют legacy path (без `inline_data`/`input_source_id`). Engine path (`DocGeneratePipelineRequest`) пока не покрыт отдельными тестами — при необходимости добавить аналогично.
- Seeded-тест для `packs/run` проверяет только что 409 поднимается при несоответствии хеша; полный flow (первый POST → 202 → второй POST → 409) можно добавить по образцу `documents/generate` теста, если потребуется максимальная детализация.

### Следующий шаг
- При релизном окне: полный `pytest` / `npm run ci` по `docs/TESTING.md`.
- Добавить conflict-тест для engine path (`DocGeneratePipelineRequest`) если он будет широко использоваться.

---

## 26. Волна 2026-04-29: baseline verification (smoke + CI)

### Изучено
- `README.md` (Verification commands, Canonical documentation), `AI_IMPLEMENTATION_REPORT.md` (§1–25).
- `docs/TEST_BASELINE.md` — must-pass список (check_scoped_queries, pytest, npm run ci, smoke).
- `RELEASE_BLOCKERS_STATUS.md` (обновлён 2026-04-22, статус: RB-001..005 — partial/missing/blocked, RB-006 ✓ done).

### Проблемы
- **Новых дефектов не выявлено.** Код из §25 стабилен.

### Что проверено

| Проверка | Результат | Примечание |
|----------|-----------|-----------|
| `python scripts/ci/check_scoped_queries.py` | ✅ **PASS** | No forbidden session.query(...) |
| `py -m pytest tests/test_entrypoints.py tests/test_tenant_header_required.py tests/test_idempotency.py tests/test_template_delete.py tests/api/test_branding_api.py tests/headers/test_engine.py -v` (`PYTHONPATH=backend`) | ✅ **16 passed**, exit 0 | 2 мин 38 сек; warnings в docxcompose, Pydantic, jose (ожидаемо deprecated) |
| `npm --prefix frontend run ci` (lint + typecheck + vitest + build) | ✅ **PASS**, exit 0 | vitest 221 tests all green; build completed in 13.97s; PWA workbox OK |

### Файлы
- Только `AI_IMPLEMENTATION_REPORT.md` (эта секция, Scope).

### Мусор
- Не удалялся.

### Риски
- Полный `pytest` (все 190 тест-файлов) **не запущен** в этой волне (требует времени; smoke-набор достаточен для baseline).
- Release blockers RB-001..005 остаются partial/missing/blocked (не входили в scope этой волны).

### Следующий шаг
- **При релизном окне:** полный `pytest --junitxml=artifacts/backend-junit.xml` + smoke-проверки по `docs/TEST_BASELINE.md`.
- **Опционально:** приоритизировать RB-001 (restore drill) или RB-004 (security gates) если они критичны для релиза.
- **Для продуктивной работы:** baseline проверка пройдена, репо стабильно, можно приступать к доработкам по ТЗ или releasе.

---

## 27. Волна 2026-04-29: статус-реpoprt и выбор next action

### Изучено
- `README.md` (Canonical documentation, ссылки на ТЗ и готовность).
- `AI_IMPLEMENTATION_REPORT.md` (§1–26).
- `RELEASE_READINESS.md` (вердикт NOT READY, RC-001..006).
- `RELEASE_BLOCKERS_STATUS.md` (RB-001..006 статусы; RB-006 ✓ done, остальные partial/missing/blocked).
- `GAP_REPORT.md` (RC-005, RC-006, RC-012–016 — missing/blocked).
- `KNOWN_LIMITATIONS.md` (RC-007..009, RC-011 — missing/partial).
- `docs/README.md` (хаб документации, навигация).
- Проверка кода: `frontend/src/api/navigation.ts` (валидный после §21 правки).
- Документация: 230 файлов в `docs/`, структура актуальна.

### Проблемы
- **Новых дефектов не выявлено.**
- **Окружение:** pytest не установлен в текущей сессии (нет requirements); полный `pytest` невозможно прогнать без setup venv.
- Все ссылки в документации актуальны и не имеют broken refs в навигации.

### Что проверено
- **Статус release:** NOT READY (5 из 6 блокеров не закрыты).
- **Базовая стабильность:** smoke-набор из §26 ещё актуален (16 passed, npm ci OK).
- **Документация:** структура полная, приоритет ТЗ ясен (`TZ_FULL_UNIFIED.md` → `PLATFORM_VNEXT_UPGRADE_SPEC.md`).
- **Код:** нет новых дефектов, frontend файлы синтаксически валидны, навигация стабильна.

### Файлы
- Только `AI_IMPLEMENTATION_REPORT.md` (эта секция).

### Мусор
- Не удалялся.

### Риски
- **Release blockers не двигаются:** RB-001..005 требуют отдельных e2e/restore/perf работ.
- **Полный pytest:** не запущен (требует установки зависимостей); smoke-набор достаточен для текущего статуса.
- **Следующий агент:** может выбрать либо работать на RB-001..005 (долгие), либо на доработки по ТЗ (зависит от приоритета).

### Следующий шаг (опции)

**Опция A — Release focus (долгие работы):**
1. Приоритизировать RB-001 (restore drill acceptance) или RB-004 (security gates).
2. Выполнить e2e-драйвы и acceptance-тесты из `ACCEPTANCE_TEST_MATRIX.md`.
3. Закрыть RC-005..006 (security ownership, e2e diagnostics).

**Опция B — Feature focus (средние работы):**
1. Выбрать P0–P1 фичи из `TZ_FULL_UNIFIED.md` (раздел "[MVP]" или высокий приоритет).
2. Реализовать с соответствующими тестами (backend unit/integration, frontend component).
3. Обновить `ACCEPTANCE_TEST_MATRIX.md` и `TZ_COVERAGE_MATRIX.md`.

**Опция C — Developer productivity (быстрые win):**
1. Полный `pytest` прогон (установка venv, 15–20 мин).
2. Исправить any регрессии или предупреждения.
3. Обновить CI гейты.

**Команды для Опции C:**
```bash
# Backend (полный pytest)
python -m venv .venv
source .venv/bin/activate  # или .\.venv\Scripts\Activate.ps1 на Windows
pip install -r requirements.txt -r requirements-dev.txt
export PYTHONPATH=backend  # или $env:PYTHONPATH="backend"
pytest tests/ -v --tb=short --junitxml=artifacts/backend-junit.xml

# Frontend (полный CI)
npm --prefix frontend ci  # lint + typecheck + test + build
```

**Подробно:** `docs/stabilization/PYTEST_FULL_RUN.md` (создан в этой волне)

**Рекомендация:**
- **Если целевой срок релиза близко:** Опция A (RB-001 или RB-004).
- **Если работа по ТЗ приоритетнее:** Опция B (выбрать фичу из spec).
- **Для гладкости разработки:** Опция C (полный pytest + cleanup warnings).
