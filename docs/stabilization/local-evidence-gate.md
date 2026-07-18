# Local-evidence quality gate (REL-1)

- **Создан:** 2026-06-29 (ТЗ `TZ_REFACTOR_AND_RELEASE.md`, блок REL-1)
- **Статус:** активная политика
- **Канон-команда:** `python scripts/ci/local_gate.py --db-only` (быстрый PG-срез) / `--full` (полный suite)

## Зачем

GitHub Actions на репозитории не используются как живой gate (исторически отключались;
см. `RELEASE_BLOCKERS_STATUS.md`). Чтобы рефакторинг и закрытие блокеров не шли «вслепую»,
нужен **воспроизводимый** прогон критичных проверок на любой машине с Docker. Это и есть
REL-1, путь (c): постоянная local-evidence политика с одной командой.

Ключевая причина гонять гейт **в Docker, а не на хосте**: репозиторий требует Python
3.12.12; на 3.13+/Windows pytest зависает на сборе (см. `CLAUDE.md`). Контейнер
(`scripts/ci/Dockerfile.gate`, `python:3.12-slim`) фиксирует версию Python и системные
зависимости — это и делает вердикт воспроизводимым и сопоставимым с CI-джобой `backend-tests`.

## Что проверяет

| Режим | Что гоняет | Зеркало CI-джобы |
|---|---|---|
| `--db-only` (по умолчанию) | `alembic upgrade heads` на чистом PG16 + все тесты с маркером `db` (enum label-drift guards, downgrade round-trip) | `alembic-postgres-upgrade` + `@pytest.mark.db` часть `backend-tests` |
| `--full` | `alembic upgrade heads` + полный бэкенд-suite с `TEST_PG_ADMIN_URL` | `backend-tests` целиком |

`--db-only` — высокосигнальный срез: именно он ловит класс багов, невидимый на SQLite
(нативные pg-enum, миграции, label drift). Это прямая проверка REL-2 / REL-3.

Оба режима сначала прогоняют **ARCH-3 boundary check** (`scripts/ci/check_context_boundaries.py`) —
быстрый stdlib-чекер границ bounded contexts: падает на новом cross-context импорте
`app.modules.* ↔ app.domains.*` (текущие протечки в allowlist). Отдельно: `make check-boundaries`.

> **Caveat по `--full`:** gate-образ не содержит LibreOffice (он тяжёлый и нужен лишь
> тестам рендеринга документов). Поэтому несколько рендер-тестов в `--full` могут
> пропускаться/падать на отсутствии бинаря — это ожидаемо и не является регрессом
> приложения. Полная проверка рендеринга остаётся за CI-образом (`Dockerfile`, где
> LibreOffice установлен).

## Как запускать

```bash
# Быстрый PG-критичный гейт (рекомендуется перед PR, трогающим миграции/enum/модели):
python scripts/ci/local_gate.py --db-only

# Полный бэкенд-suite (зеркало CI):
python scripts/ci/local_gate.py --full

# Доп. аргументы pytest — после двойного дефиса:
python scripts/ci/local_gate.py --db-only -- -k enum -x

# Не пересобирать образ (если requirements не менялись и образ уже собран):
python scripts/ci/local_gate.py --db-only --no-build

# Оставить PostgreSQL запущенным для ручной отладки:
python scripts/ci/local_gate.py --db-only --keep-db
```

Make-обёртки: `make gate` (= `--db-only`) и `make gate-full` (= `--full`).

## Артефакт-вердикт

Каждый прогон пишет `artifacts/local-gate/summary.json`:

```json
{
  "gate": "local-evidence",
  "mode": "db-only",
  "verdict": "green",
  "exit_code": 0,
  "python": "3.12 (gate image)",
  "postgres": "postgres:16",
  "started_utc": "...",
  "finished_utc": "...",
  "command": "python scripts/ci/local_gate.py --db-only"
}
```

Этот JSON — и есть «reproducible evidence» по политике из `RELEASE_BLOCKERS_STATUS.md`
(§ «Evidence policy»): команда + версии Python/PG зафиксированы, прогон повторяем.

## Политика (REL-1, путь c)

1. **Local evidence — достаточное основание** для закрытия релиз-критичных блокеров,
   пока соблюдены три условия из `RELEASE_BLOCKERS_STATUS.md` § Evidence policy:
   воспроизводимость (точная команда + версии), проверка кода (тесты/аудит-скрипты),
   объявленные caveats.
2. **Каноническая команда** этого гейта — `python scripts/ci/local_gate.py` (см. выше).
   Она заменяет «ручной» прогон pytest на хосте как источник истины по PG-корректности.
3. **Если GitHub Actions снова станут доступны** — гейт не отменяется, а становится
   локальным дублёром CI; провизорные закрытия RB-002/003/005 должны быть
   ре-валидированы против реальных runs (см. обязательство в `RELEASE_BLOCKERS_STATUS.md`).

## Требования окружения

- Docker (Desktop / Engine). Проверка: `docker version`.
- Доступ к Docker Hub для первичного `pull` `postgres:16` и `python:3.12-slim`
  (дальше всё из кэша).
- Для Windows: bind-mount рабочего дерева делается по нативному пути (`D:\...`),
  поэтому запускайте из PowerShell/CMD, а не из Git-Bash (он манглит путь в `/d/...`).
