# prt-ot-doc

Платформа генерации документов по охране труда (ОТ), промышленной безопасности (ПБ), экологии и смежным направлениям. Репозиторий включает FastAPI-бэкенд, Celery-воркеры, PostgreSQL, Redis, MinIO/S3, фронтенд на React/Vite и Docker-инфраструктуру для локального запуска и CI.

## Оглавление
1. [Архитектура](#архитектура)
2. [Требования](#требования)
3. [10-минутный запуск](#10-минутный-запуск)
4. [Установка](#установка)
5. [Конфигурация окружения](#конфигурация-окружения)
6. [Локальный запуск](#локальный-запуск)
7. [Docker Compose](#docker-compose)
8. [Makefile](#makefile)
9. [Тесты и качество](#тесты-и-качество)
10. [CI/CD](#cicd)
11. [Безопасность](#безопасность)
12. [Troubleshooting](#troubleshooting)
13. [API-примеры](#api-примеры)
14. [Полезные ссылки](#полезные-ссылки)

## Архитектура
- **Backend** (`app/`, `backend/`) — REST API на FastAPI, доменные сервисы, Alembic-миграции, интеграции.
- **Worker** (`app/tasks`, `scripts/`) — Celery-очереди `default`, `notifications`, `pdf` для асинхронной генерации документов.
- **Object storage** — MinIO/S3 для шаблонов и итоговых документов.
- **Очередь** — Redis как брокер и хранилище результатов Celery.
- **Frontend** (`frontend/`) — Vite + React SPA (Zustand, API-клиент).
- **Инфраструктура** (`docker-compose.yml`, `infra/`, `proxy/`) — сервисы разработки, Nginx-прокси, healthchecks.

Архитектурные детали: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Публичный контракт API: [docs/openapi.yaml](docs/openapi.yaml) и снапшот [docs/openapi_snapshot_v01.json](docs/openapi_snapshot_v01.json).

## Требования
- Python 3.12.6 (зафиксирован в `.python-version`)
- Poetry 1.8.3 (опционально, для `make`/Poetry-процессов)
- Docker и Docker Compose v2
- Node.js 20 (для фронтенда)

## 10-минутный запуск
Последовательность от клона до первого успешного запуска.

```bash
# 0. Предустановите Python 3.12.6, Node.js 20, Docker, Docker Compose v2

# 1. Клонируйте проект
git clone <repo-url>
cd prt_ot_doc

# 2. Подготовьте окружение
cp .env.example .env
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip

# 3. Установите зависимости (runtime + dev)
pip install -r requirements-dev.txt

# 4. Поднимите инфраструктуру
docker compose up -d db redis minio

# 5. Примените миграции и запустите тесты
python -m alembic upgrade head
pytest

# 6. Запустите API
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Установка
> *Допущение: базовая разработка ведётся на Linux/macOS. Для Windows приведены PowerShell-аналоги.*

1. **Создайте и активируйте виртуальное окружение.**

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   ```

2. **Установите зависимости приложения.**

   ```bash
   pip install -r requirements.txt
   ```

3. **Установите зависимости для разработки.**

   ```bash
   pip install -r requirements-dev.txt
   ```

4. **(Опционально) используйте Poetry и Makefile.**

   ```bash
   make install
   poetry run pre-commit install
   ```

5. **Подготовьте переменные окружения.**

   ```bash
   cp .env.example .env
   ```

PowerShell-эквивалент:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip

pip install -r requirements.txt
pip install -r requirements-dev.txt

make install
poetry run pre-commit install

Copy-Item .env.example .env
```

## Конфигурация окружения
Все параметры перечислены в [`.env.example`](./.env.example). Группы переменных:
- **Core** — URL приложения, trusted hosts, CORS.
- **БД** — DSN для SQLAlchemy/Alembic и учётные данные PostgreSQL.
- **Redis** — broker/result backend для Celery.
- **S3/MinIO** — эндпоинт, ключи доступа, bucket.
- **JWT** — issuer/audience, TTL, ключи.
- **Документооборот** — лимиты конвертации, очереди Celery, LibreOffice.
- **Observability** — логирование/метрики.
- **Frontend** — `VITE_*` переменные для SPA.

Алгоритм: `cp .env.example .env`, затем изменяйте только чувствительные значения (секреты, DSN, хосты). В продакшене используйте секрет-хранилища.

## Локальный запуск
### Backend (uvicorn)
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Healthchecks
curl -s http://127.0.0.1:8000/health | jq
curl -s http://127.0.0.1:8000/ready | jq
```

### Celery воркеры
```bash
# Основные воркеры
celery -A app.services.celery_app.celery_app worker \
  --queues default,notifications --loglevel INFO

# PDF-воркер
celery -A app.services.celery_app.celery_app worker \
  --queues pdf --loglevel INFO
```

### Frontend
```bash
cd frontend
npm install
npm run dev  # http://localhost:5173
```

## Docker Compose
```bash
cp .env.example .env
docker compose up --build

# API доступен на localhost:8000
curl -s http://127.0.0.1:8000/health | jq

# Остановка и очистка
docker compose down -v
```

> Postgres, Redis, MinIO и ClamAV не пробрасываются наружу. Обязательный порт — `8000/tcp` (API). Фронтенд и прокси можно включить дополнительно (`5173`/`8080`).

## Makefile
| Команда | Назначение |
| --- | --- |
| `make install` | `poetry install --with dev --no-interaction` |
| `make lint` | `ruff` + `black --check` для `app`, `tests`, `scripts` |
| `make format` | автофикс ruff/black |
| `make test` | Pytest (unit + интеграционные) |
| `make contract` | `pytest -m contract` (OpenAPI-валидации) |
| `make run` | Uvicorn локального API |
| `make build` | Сборка poetry-пакета |
| `make clean` | Очистка кешей и артефактов |
| `make up` | `docker compose up -d --build` |
| `make down` | `docker compose down -v` |

## Тесты и качество
- `make lint` — ruff + black.
- `make format` — автоисправление стиля.
- `make test` — pytest (unit + интеграционные).
- `make contract` — OpenAPI контрактные проверки.
- Frontend (из `frontend/`): `npm run lint`, `npm run test`, `npm run build`.

## CI/CD
GitHub Actions [`ci.yml`](.github/workflows/ci.yml) выполняет:
1. Установку Python 3.12.6 и Poetry с кешированием зависимостей.
2. Запуск Postgres/MinIO как сервисов Actions.
3. `make install`, миграции Alembic и ожидание готовности сервисов.
4. `make lint`, `make test`, `make contract`.

## Безопасность
- Секреты и ключи не хранятся в репозитории (используйте .env или секрет-хранилища).
- Nginx-прокси (`proxy/nginx.conf`) добавляет базовые security-заголовки и gzip.
- Файлы, прошедшие антивирусную проверку, доступны по подписанным ссылкам.

## Troubleshooting
| Проблема | Решение |
| --- | --- |
| `LIBREOFFICE_BIN` не найден | Убедитесь, что LibreOffice установлен и путь указан в `.env`. Для dev используйте контейнер `libreoffice`. |
| Celery-задачи висят | Проверьте доступность Redis и совпадение `WORKER_QUEUES` / `PDF_WORKER_QUEUE`. |
| Ошибки подключения к MinIO | Проверьте `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` и что сервис запущен (`docker compose logs minio`). |
| 403 на API-запросы | Проверьте JWT issuer/audience и корректность ключей. |

## API-примеры
```bash
# Запуск пакета документов
http --json POST :8000/api/v1/packs/run \
  Authorization:"Bearer <token>" \
  Idempotency-Key:"$(uuidgen)" \
  pack_code==OT_ENTER_SITE \
  company_id==1 \
  site_id==1 \
  person_ids:='[123]' \
  data:='{"shift": "day"}'

# Проверка статуса
http GET :8000/api/v1/packs/runs/<run_id> Authorization:"Bearer <token>"
```

## Полезные ссылки
- [OpenAPI спецификация](./docs/openapi.yaml)
- [ER-диаграмма](./docs/erd.puml)
- [Сценарии бизнес-логики](./docs/Backend_TZ.md)
- [Roadmap](docs/NEXT_FEATURES.md)
