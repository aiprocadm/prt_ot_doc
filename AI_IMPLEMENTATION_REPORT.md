# AI / Engineering implementation report

- **Date (UTC):** 2026-04-28 (обновлено)  
- **Scope:** documentation inventory, P0 test harness fix, testing doc repair; full-platform audit is **not** completed in a single pass (see «Ограничения»). Последняя волна: **процедура обновления вердикта релиза (`RELEASE_READINESS` + `RELEASE_BLOCKERS_STATUS`, CI)**; ранее — ссылка на готовность в README, **P1 Vitest**, хаб `docs/spec/README`, **P1 frontend lint**.
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
