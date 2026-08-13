# CLAUDE.md

Оперативный гид для Claude Code в этом репозитории. Workflow «по ТЗ» — в [AGENTS.md](AGENTS.md). Полный контекст и список доков — в [README.md](README.md).

**«Продолжай по ТЗ» = сверка → выбор → код** (протокол — `docs/spec/TZ_FULL_UNIFIED.md` §0.2): статусы `done` в `TZ_COVERAGE_MATRIX.md` и «Следующий точный шаг» в `AI_IMPLEMENTATION_REPORT.md` — заявления прошлых волн, не факты. Перед выбором работы обязательно сверить их с реальным кодом и тестами (evidence-пути из строк матрицы + прогон тестов строки + хвост последнего handoff), вынести вердикты «сделано / не сделано / переделать» и зафиксировать расхождения в матрице до новой работы. Ответ начинать с блока «Сверка с ТЗ».

## What this repo is

B2B multi-tenant SaaS для охраны труда / промбезопасности / экологии / документооборота / ЭДО / обучения / СИЗ / рисков / инцидентов / CRM / billing / client portal. Production-minded modular monolith.

## Architecture map

- **Backend** (Python 3.12 / FastAPI / SQLAlchemy / Alembic / Celery) — `backend/app/`
  - App factory: `backend/app/api/app.py`
  - ASGI entrypoint: `backend/app/main.py`
  - Migrations: `backend/app/migrations/` (config — `alembic.ini` рядом)
  - Celery app: `app.services.celery_app:celery_app` (не `backend.app.worker` — там только bootstrap)
- **Frontend** (React 18 / Vite / TypeScript / Zustand / TanStack Table / Radix UI / Tailwind) — `frontend/`
  - Entry: `frontend/src/main.tsx`
  - Router: `frontend/src/router/AppRouter.tsx`
  - Единственный активный manifest — `frontend/package.json`
- **CLI wrapper**: `./ptd --help`
- **Tests**: `tests/`, `backend/tests/`, `integration_tests/` (см. `pyproject.toml::testpaths`)

`app/__init__.py` в корне — legacy compat shim для `import app.*`. Канон — `backend/app/*`. `prt_ot_doc-main/` в корне игнорируется (gitignored) — не распаковывайте архив второй раз внутрь репо.

## Quick start

```bash
make dev-lite                       # рекомендованный путь: dockerless
# либо кросс-платформенно:
python scripts/dev_lite.py          # backend :8000 + frontend :5173
python scripts/dev_lite.py --auto-kill-ports   # если порты заняты
```

Default test login (заполняется `backend/app/services/dev_bootstrap.py` при первом запуске):
- tenant: `demo` · email: `admin@example.com` · password: `admin123`

## PYTHONPATH=backend invariant

Любая ручная команда вне `make` / `pytest` обязана явно задавать `PYTHONPATH=backend` — иначе `import app.*` падает. В `pyproject.toml` для pytest это уже зашито (`pythonpath = ["backend", "."]`), но ручные запуски — нет:

```bash
# Unix
PYTHONPATH=backend uvicorn app.main:app --port 8000
PYTHONPATH=backend alembic -c backend/app/migrations/alembic.ini upgrade heads
PYTHONPATH=backend celery -A app.services.celery_app:celery_app worker -Q default,pdf

# Windows PowerShell
$env:PYTHONPATH="backend"; uvicorn app.main:app --port 8000
```

## Running tests

The repo requires Python **3.12.12**. The local machine may have a different version.

### Determine which Python to use

Before running any tests, detect available Python:

```bash
python3.12 -m pytest ...        # if python3.12 is available
python3 -m pytest ...           # fallback: use whatever python3 is present
```

If `python3.12` is not found, run tests with the system Python (`python3` / `python`) and note the version mismatch in your output — **do not abort**. CI will run the canonical pipeline with 3.12.12.

### Version mismatch policy

- **Do not fail or stop** when Python 3.12 is absent. Run tests with the available Python and report results.
- **Do not run `make cs:test`** (full 1200+ test suite) unless Docker and Python 3.12.12 are both confirmed available — that target requires both.
- For partial local runs, prefer targeted pytest invocations (e.g. `python3 -m pytest tests/unit/`) over full Make targets.
- CI is the source of truth for full test results.

### Quick check

```bash
python3 --version          # see what's available
python3.12 --version 2>/dev/null && echo "3.12 ok" || echo "3.12 not found — using fallback"
```

## CI status: ⚠️ ВЫКЛЮЧЕН ВРУЧНУЮ до обновления лимитов; канонический gate — local-evidence

**13.08.2026 все 6 workflow переведены в `disabled_manually`** (`gh workflow disable`) по решению владельца: бесплатная квота минут GitHub исчерпана. Файлы в `.github/workflows/` НЕ переименовывались, поэтому в git диффа нет — тишину CI легко принять за поломку. Включить обратно: `gh workflow enable <id>` для CI `234511511`, DAST `322926344`, E2E smoke `255902927`, Final Acceptance `283085436`, Perf Baseline `263698872`, Restore Drill `263378523`.

**Как отличить «кончились лимиты» от «сломан код»:** при исчерпанной квоте прогон падает за 2–11 секунд, у заданий ПУСТОЙ список шагов и нет логов (`log not found`) — раннер не стартовал вовсе.

**Бюджет минут (замер 13.08.2026, PR #891).** Считать так: длительность каждого задания × тариф ОС (Linux ×1, Windows ×2, macOS ×10, округление вверх до минуты) — timing-эндпоинт GitHub отдаёт нули. Было: PR 140 минут + push в main 160 = **~300 за один влитый срез**. Стало: push в main больше НЕ перепроверяет то, что только что прошло в PR (**~16 минут**), macOS/Windows и медленные сканеры ушли в еженедельный полный прогон (`schedule`, понедельник 02:00 UTC) и запуск по кнопке. Итог — **~156 минут за срез вместо 300**. Осколки бэкенд-тестов НЕ объединяли намеренно: они существуют ради памяти раннера и коротких заданий (см. комментарий у `backend-tests`), объединение купило бы минуты ценой нестабильности. Если понадобится ужаться ещё — в `ci.yml` у выхода `full` описан однострочный переключатель (бэкенд-тесты уходят с PR в еженедельный прогон, ~1000 минут в месяц); это смена политики гейта, решение владельца.

При этом **канонический gate — воспроизводимый локальный прогон** (постоянная local-evidence политика, REL-1 вариант (c); см. `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` → «Evidence policy (PERMANENT)»): локальный pytest / `make gate` = источник истины, результаты GHA — дополнительная непрерывная защита. Поэтому работа по срезам идёт как обычно: доказательство волны — локальный полный прогон + db-гейт в теле PR. Текущий вердикт релиза и блокеры:

- [RELEASE_READINESS.md](RELEASE_READINESS.md) — вердикт + RC-критерии
- [docs/stabilization/RELEASE_BLOCKERS_STATUS.md](docs/stabilization/RELEASE_BLOCKERS_STATUS.md) — каноника блокеров

Frontend gates перед PR:
```bash
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
```

## Canonical docs (где брать контекст до кода)

1. [README.md](README.md) — карта репо и quick start
2. [AGENTS.md](AGENTS.md) — правило «по ТЗ» (точка входа для агентов)
3. [docs/spec/TZ_FULL_UNIFIED.md](docs/spec/TZ_FULL_UNIFIED.md) — канон ТЗ (раздел A=MVP, B=vNext, E=правила доработки)
4. [AI_IMPLEMENTATION_REPORT.md](AI_IMPLEMENTATION_REPORT.md) — handoff-журнал; «Следующий точный шаг» в последнем блоке
5. [docs/TESTING.md](docs/TESTING.md) — testing strategy и merge gates
6. [docs/troubleshooting.md](docs/troubleshooting.md) — типовые локальные ошибки

## Local gotchas

- **Python 3.13 + Windows**: pytest может зависнуть на сборе. Используйте Py3.12.12 локально (см. `.python-version`).
- **Cygwin / Git-Bash на Windows**: `scripts/smoke.sh` падает с exit 256 (path mangling). Запускайте из PowerShell или WSL.
- **Git worktrees**: 6 копий CLAUDE.md в `Создание платформы по ОТ/<adj-name>/CLAUDE.md` — это активные worktrees. Отдельно их не редактируйте; обновление корня тянется через `git checkout` в каждом worktree.
- **Не запускайте `make cs:test`** без Docker и Py3.12.12 — он разворачивает контейнеры и крутит ~1200 тестов.
- **`make dev-lite` идемпотентен**: переинициализирует SQLite-схему и demo-tenant. Чтобы сбросить локальное состояние — `make cs:reset` (удаляет `dev.db`, `.local_storage`, `frontend/coverage`).
