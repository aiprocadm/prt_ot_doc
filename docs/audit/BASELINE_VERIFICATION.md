# Baseline verification (fail-first)

Дата прогона: 2026-02-18
Среда: GitHub Codespaces / dockerless profile

## Выполненные команды

1. `make cs:reset`
2. `cp .env.example .env`
3. `make cs:dev`
4. `make cs:test`
5. `source .venv/bin/activate && pytest --collect-only -q`
6. `npm --prefix frontend test`

## Результаты

### 1) `make cs:reset`
- Статус: **OK**
- Очистка выполнена: `dev.db`, `.local_storage`, `frontend/coverage`.

### 2) `cp .env.example .env`
- Статус: **OK**
- `.env` создан из шаблона.

### 3) `make cs:dev`
- Статус: **OK** (после первичной установки зависимостей)
- Поднялись сервисы:
  - backend: `http://localhost:8000`
  - frontend: `http://localhost:5173`
- Наблюдения (не блокеры):
  - предупреждение о отсутствии `soffice` (LibreOffice) в окружении;
  - предупреждение про locale `ru-RU` недоступен;
  - используются development JWT keys (ожидаемо для dev).

### 4) `make cs:test`
- Статус: **OK**
- Backend pytest: `287 passed, 1 skipped`.
- Frontend vitest: `23 passed`, `44 passed`.
- Наблюдения:
  - много предупреждений deprecation/SAWarning/React act warnings;
  - тесты при этом зелёные.

### 5) `pytest --collect-only -q`
- Статус: **OK**
- Коллекция тестов стабильна, обнаружены backend/integration/unit/contract test suites.

### 6) `npm --prefix frontend test`
- Статус: **OK**
- Vitest проходит полностью, покрытие формируется.
- Наблюдения:
  - предупреждения React Router future flags;
  - предупреждения об `act(...)` в части компонентных тестов.

## Fail-first фиксация
- Критичных падений по baseline-командам не обнаружено.
- Основные потенциальные риски для новичков:
  1. долгий cold-start на первом `make cs:dev` из-за установки Python/Node deps;
  2. отсутствие `soffice` в окружении (не блокирует текущий dev flow, но влияет на прод-паритет PDF пайплайна);
  3. шум предупреждений в тестах затрудняет чтение логов.

## Воспроизведение
- Выполнить команды в указанном порядке из раздела «Выполненные команды».
- Для входа в UI указать в `.env`:
  - `ADMIN_BOOTSTRAP=1`
  - `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_TENANT`.
