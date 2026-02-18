# Repository Structure

## Top-level
- `backend/` — FastAPI backend, модели, сервисы, миграции, API.
- `frontend/` — React/Vite UI (feature-oriented pages/features/stores/components).
- `tests/`, `integration_tests/` — backend unit/integration/regression tests.
- `docs/` — архитектура, runbook, спецификации, аудиты, ADR.
- `scripts/` — dev/test утилиты и обёртки для dockerless/CI.
- `infra/` — docker-compose и Dockerfiles для полного локального контура.
- `proxy/` — nginx-конфигурации для reverse proxy сценариев.
- `config/` — контейнерные конфиги для postgres/minio/libreoffice/redis профилей.

## Важные каталоги
### `scripts/`
- `dev_lite.sh` — dockerless запуск backend+frontend.
- `test_lite.sh` / `pytest.sh` — стабильный запуск тестов в `.venv`.
- `dockerless_env.sh` / `configure_dockerless_env.sh` — подготовка env под Codespaces.
- `seed_data.py` — наполнение dev-данными.

### `proxy/`
- Nginx конфиги для фронта и API при reverse proxy топологиях.

### `infra/`
- Compose/образы для полного окружения (не обязательны для dockerless onboarding).

### `integration_tests/`
- Сквозные проверки интеграционных сценариев и фабрик интеграций.

## Канонические команды для новичка
1. `make cs:reset`
2. `cp .env.example .env`
3. `make cs:dev`
4. `make cs:test`
