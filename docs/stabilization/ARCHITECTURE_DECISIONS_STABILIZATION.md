# Архитектурные решения (стабилизация)

## ADR-S01: Staging и секреты инфраструктуры

**Контекст:** Production уже запрещал dev-default для SECRET_KEY, Postgres, S3. Staging часто копирует docker-compose с теми же значениями.

**Решение:** Для `APP_ENV=staging` применить те же проверки, что и для production, по полям: `SECRET_KEY`, `POSTGRES_PASSWORD`, `S3_*`, `S3_BACKEND` (не `memory`).

**Не входит:** Обязательные кастомные JWT-ключи для staging — остаётся предупреждение и dev-пара как в development, чтобы не ломать быстрые стенды. Для «настоящего» staging с RS256 отдельно задать `PRIVATE_KEY_PEM`/`PUBLIC_KEY_PEM`.

**Последствия:** Старые staging-окружения с `change-me` и `prt_local_*` не стартуют без обновления env.

---

## ADR-S02: Ошибки bootstrap — `SettingsError` вместо `RuntimeError`

**Контекст:** Пропущенные обязательные переменные при `bootstrap()` выбрасывали `RuntimeError`.

**Решение:** Единый тип `SettingsError` для всех ошибок конфигурации при старте.

**Последствия:** `SettingsError` наследует `RuntimeError`, поэтому существующие `except RuntimeError` продолжают ловить ошибки bootstrap; для явности предпочтительно `except SettingsError`.

---

## ADR-S03: Ruff в CI — отложен до устранения бэклога

**Контекст:** `ruff check backend/app` выявляет десятки исторических нарушений (E402 side-effect imports в `db/base.py`, F401 в `__init__.py` пакетов, E741 и т.д.).

**Решение:** Не включать полный ruff gate до поэтапного исправления или явного ограничения scope (например, только `api/v1`).

**Альтернатива:** `ruff check --select F821,F401` как узкий gate.

---

## ADR-S04: Импорт `sqlalchemy.func` в giant router

**Контекст:** Файл `api/v1/router.py` содержит много inline SQL; отсутствие `func` — дефект времени выполнения.

**Решение:** Минимальный fix — импорт. Долгосрочно — вынести запросы в repository/service слой.
