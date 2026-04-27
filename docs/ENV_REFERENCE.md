# ENV_REFERENCE — Справочник переменных окружения

Полный список переменных окружения, читаемых приложением из `.env` / OS-среды.
Источник истины: `backend/app/core/config.py` (класс `Settings`).

---

## Приложение

| Переменная | Псевдоним / Alias | По умолчанию | Описание |
|---|---|---|---|
| `APP_NAME` | — | `prt-ot-doc` | Имя приложения в логах и метаданных. |
| `APP_ENV` | — | `development` | Режим запуска: `development` \| `staging` \| `production` \| `test`. |
| `APP_DEBUG` | — | `false` | Включить отладочный режим FastAPI. |
| `APP_RUN_MODE` | — | `docker` | Режим запуска: `docker` \| `dockerless`. Влияет на Redis-поведение. |
| `AUDIT_ENABLED` | — | `true` | Включить audit-log операций. |
| `API_PREFIX` | — | `/api` | Префикс всех API-маршрутов. |
| `API_V1_PREFIX` | — | `/api/v1` | Префикс маршрутов версии v1. |
| `APP_TRUSTED_HOSTS` | `ALLOWED_HOSTS` | `localhost,127.0.0.1,::1,testserver` | Разрешённые HTTP-хосты (CSV). |
| `APP_CORS_ORIGINS` | `ALLOWED_ORIGINS` | `http://localhost,http://localhost:5173,...` | Допустимые CORS-источники (CSV). Нельзя использовать `*` совместно с `APP_CORS_ALLOW_CREDENTIALS=true`. |
| `APP_CORS_ALLOW_CREDENTIALS` | — | `true` | Разрешить куки/credentials в CORS-запросах. |
| `DEFAULT_LOCALE` | — | `ru-RU` | Локаль по умолчанию для i18n. |
| `DEFAULT_TIMEZONE` | — | `Europe/Moscow` | Временная зона для дат/логов. |

---

## База данных

| Переменная | По умолчанию | Описание |
|---|---|---|
| `DATABASE_URL` | _(строится из POSTGRES_*)_ | Полный DSN для SQLAlchemy (`postgresql+asyncpg://...`). Если задан — перекрывает POSTGRES_* переменные. |
| `POSTGRES_HOST` | `postgres` | Хост PostgreSQL. |
| `POSTGRES_PORT` | `5432` | Порт PostgreSQL. |
| `POSTGRES_DB` | `documents` | Имя базы данных. |
| `POSTGRES_USER` | `app` | Пользователь БД. |
| `POSTGRES_PASSWORD` | `change_me` | Пароль БД. **Обязателен к смене в staging/production.** |
| `DATABASE_ECHO` | `false` | Логировать SQL-запросы SQLAlchemy. |
| `DEFAULT_TENANT_SLUG` | `public` | Slug тенанта по умолчанию. Допустимые символы: `[a-z0-9\-_]`. |
| `SHARED_SCHEMA` | `public` | Имя общей PostgreSQL-схемы. |
| `RUNTIME_SCHEMA_BOOTSTRAP` | `false` | Разрешить авто-создание схем в рантайме. Отключено по умолчанию. |

---

## Хранилище объектов (S3 / MinIO)

| Переменная | По умолчанию | Описание |
|---|---|---|
| `STORAGE_BACKEND` | `memory` | Бэкенд: `local` \| `s3` \| `memory`. |
| `STORAGE_ROOT` | `./.local_storage` | Корневая папка для `local`-бэкенда. |
| `S3_BACKEND` | `memory` | Внутренний S3-режим: `memory` \| `minio` \| `local`. Устанавливается автоматически при смене `STORAGE_BACKEND`. |
| `S3_ENDPOINT` | `http://minio:9000` | URL S3-совместимого хранилища. |
| `S3_BUCKET` | `documents` | Имя бакета. |
| `S3_ACCESS_KEY` | `prt_local_access` | Access key. **Обязателен к смене в staging/production.** |
| `S3_SECRET_KEY` | `prt_local_secret` | Secret key. **Обязателен к смене в staging/production.** |
| `S3_SECURE` | `false` | Использовать HTTPS для S3. |
| `PRESIGN_DOWNLOAD_TTL_SECONDS` | `900` | TTL presigned URL для скачивания (60–3600 с). |

---

## Безопасность / JWT

| Переменная | По умолчанию | Описание |
|---|---|---|
| `SECRET_KEY` | `change-me` | Ключ подписи сессий/CSRF. **Обязателен к смене в staging/production.** |
| `PORTAL_TOKEN_SALT` | `portal-salt` | Соль для portal-токенов клиентского доступа. |
| `JWT_ISSUER` | `prt-ot-doc` | Значение поля `iss` в JWT. |
| `JWT_AUDIENCE` | `prt-ot-doc-clients` | Значение поля `aud` в JWT. |
| `JWT_ALG` | `RS256` | Алгоритм подписи JWT. |
| `JWT_ACCESS_TTL_MIN` | `30` | Время жизни access-токена (минуты). |
| `JWT_REFRESH_TTL_D` | `7` | Время жизни refresh-токена (дни). |
| `PRIVATE_KEY_PEM` | _(auto-generated в dev)_ | RSA private key PEM для подписи JWT. **Обязателен в staging/production.** |
| `PUBLIC_KEY_PEM` | _(auto-generated в dev)_ | RSA public key PEM для верификации JWT. **Обязателен в staging/production.** |
| `INBOUND_WEBHOOK_HMAC_SECRET` | `""` | HMAC-секрет для верификации входящих вебхуков. **Обязателен в staging/production.** |

> **Важно:** в `staging`/`production` приложение откажется стартовать, если `PRIVATE_KEY_PEM`/`PUBLIC_KEY_PEM` не заданы или совпадают с дев-значениями.

---

## Redis / Celery / Брокер

| Переменная | По умолчанию | Описание |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | URL брокера Redis (Celery + rate limiting). |
| `REDIS_RESULT_URL` | _(=`REDIS_URL`)_ | URL Celery result backend. По умолчанию совпадает с `REDIS_URL`. |
| `WORKER_QUEUES` | `default` | Очереди Celery-воркера (CSV). Очередь `pdf` добавляется автоматически. |
| `CELERY_TASK_SOFT_TIME_LIMIT` | `300` | Мягкий лимит времени задачи (секунды). |
| `CELERY_TASK_TIME_LIMIT` | `600` | Жёсткий лимит времени задачи (секунды). |
| `CELERY_TASK_MAX_RETRIES` | `5` | Максимум повторных попыток задачи. |
| `CELERY_RETRY_BACKOFF_SECONDS` | `5` | Начальная задержка повтора (секунды). |
| `CELERY_RETRY_BACKOFF_MAX_SECONDS` | `300` | Максимальная задержка повтора (секунды). |
| `CELERY_EAGER` | `false` | Выполнять задачи синхронно (для тестов). |

---

## Outbox

| Переменная | По умолчанию | Описание |
|---|---|---|
| `OUTBOX_POLL_INTERVAL` | `5.0` | Интервал опроса outbox-таблицы (секунды). |
| `OUTBOX_IN_PROGRESS_TIMEOUT_SECONDS` | `900.0` | Таймаут для зависших outbox-записей. |
| `OUTBOX_MAX_ATTEMPTS` | `10` | Максимум попыток доставки outbox-события. |
| `OUTBOX_RETRY_BACKOFF_SECONDS` | `5.0` | Начальная задержка повтора outbox. |
| `OUTBOX_RETRY_BACKOFF_MAX_SECONDS` | `600.0` | Максимальная задержка повтора outbox. |

---

## LibreOffice / PDF

| Переменная | По умолчанию | Описание |
|---|---|---|
| `LIBREOFFICE_BIN` | `soffice` | Путь к бинарному файлу LibreOffice. |
| `PDF_FALLBACK_MODE` | `auto` | Режим fallback при ошибке PDF: `auto` \| `always` \| `never`. |
| `PDF_LIBREOFFICE_TIMEOUT_SECONDS` | `120` | Таймаут одной попытки конвертации. |
| `PDF_LIBREOFFICE_MAX_ATTEMPTS` | `4` | Максимум попыток конвертации. |
| `PDF_LIBREOFFICE_RETRY_BACKOFF_SECONDS` | `1.0` | Начальная задержка между попытками. |
| `PDF_LIBREOFFICE_RETRY_BACKOFF_MAX_SECONDS` | `30.0` | Максимальная задержка между попытками. |
| `PDF_WORKER_QUEUE` | `pdf` | Имя Celery-очереди для PDF-задач. |
| `PDF_WORKER_CONCURRENCY` | `2` | Concurrency PDF-воркера. |
| `DOC_PIPELINE_ENABLE_QR` | `false` | Включить вставку QR-кода в пайплайне. |
| `DOC_PIPELINE_ENABLE_WATERMARK` | `false` | Включить водяной знак. |
| `DOC_PIPELINE_WATERMARK_TEXT` | `CONFIDENTIAL` | Текст водяного знака. |

---

## Загрузка файлов

| Переменная | По умолчанию | Описание |
|---|---|---|
| `MAX_UPLOAD_SIZE` / `MAX_UPLOAD_BYTES` | `20971520` (20 МБ) | Максимальный размер загружаемого файла (байты). |
| `FILE_ALLOWED_MIME` | `application/pdf,application/msword,...` | Допустимые MIME-типы (CSV). |
| `FILE_ALLOWED_EXTENSIONS` | `pdf,doc,docx,txt,png,jpg,jpeg` | Допустимые расширения файлов (CSV). |
| `JSON_MAX` | `1048576` (1 МБ) | Максимальный размер JSON-тела запроса (байты). |
| `DOCUMENT_PAYLOAD_MAX_BYTES` | `1048576` | Максимальный размер payload генерации документа. |
| `DOCUMENT_BATCH_MAX_ROWS` | `500` | Максимум строк в batch-генерации. |

---

## Вебхуки (исходящие)

| Переменная | По умолчанию | Описание |
|---|---|---|
| `WEBHOOK_URLS_DOCUMENT_CREATED` | `""` | CSV URL для события `document.created`. |
| `WEBHOOK_URLS_DOCUMENT_GENERATED` | `""` | CSV URL для события `document.generated`. |
| `WEBHOOK_URLS_DOCUMENT_SIGNED` | `""` | CSV URL для события `document.signed`. |
| `WEBHOOK_URLS_SIGNED` | `""` | Alias для `document.signed`. |
| `WEBHOOK_URLS_DOCUMENT_EXPORTED` | `""` | CSV URL для события `document.exported`. |
| `WEBHOOK_URLS_EXPORTED` | `""` | Alias для `document.exported`. |
| `WEBHOOK_URLS_RISK_ASSESSED` | `""` | CSV URL для события `risk.assessed`. |
| `WEBHOOK_URLS_PPE_ISSUED` | `""` | CSV URL для события `ppe.issued`. |
| `WEBHOOK_URLS_PPE_RETURNED` | `""` | CSV URL для события `ppe.returned`. |
| `WEBHOOK_URLS_TRAINING_COMPLETED` | `""` | CSV URL для события `training.completed`. |
| `WEBHOOK_URLS_TRAINING_ASSIGNED` | `""` | CSV URL для события `training.assigned`. |
| `WEBHOOK_TIMEOUT_SECONDS` | `10.0` | Таймаут доставки вебхука (секунды). |

---

## Rate limiting

| Переменная | По умолчанию | Описание |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `true` | Включить rate limiting. |
| `RATE_LIMIT_STORAGE_URI` | `memory://` | URI хранилища счётчиков. Используйте `redis://...` в production. |
| `RATE_LIMIT_LOGIN_PER_IDENTITY` | `5/minute` | Лимит попыток входа на одного пользователя. |
| `RATE_LIMIT_UPLOAD_PER_TENANT` | `10/minute` | Лимит загрузок на тенант. |
| `RATE_LIMIT_GENERATE_PER_TENANT` | `20/minute` | Лимит генераций документов на тенант. |

---

## ClamAV

| Переменная | По умолчанию | Описание |
|---|---|---|
| `CLAMAV_HOST` | `clamav` | Хост ClamAV-демона. |
| `CLAMAV_PORT` | `3310` | Порт ClamAV. |
| `CLAMAV_TIMEOUT` | `30.0` | Таймаут подключения к ClamAV (секунды). |
| `CLAMAV_UNIX_SOCKET` | `null` | Путь к Unix-сокету ClamAV (приоритет над host:port). |
| `CLAMAV_QUEUE_URL` | `memory://` | URL очереди для ClamAV-задач. |
| `CLAMAV_SCAN_QUEUE` | `clamav.scan` | Имя очереди сканирования. |
| `CLAMAV_QUARANTINE_QUEUE` | `clamav.quarantine` | Имя очереди карантина. |

---

## Observability / HTTP

| Переменная | По умолчанию | Описание |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Уровень логирования (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `LOG_JSON` | `true` | Использовать JSON-форматтер для логов. |
| `ENABLE_METRICS` | `true` | Включить эндпоинт `/metrics`. |
| `ENABLE_OPENAPI_DOCS` | `true` | Включить Swagger UI / ReDoc. **Автоматически отключается в `production`.** |
| `ENABLE_GZIP` | `true` | Включить GzipMiddleware. |
| `ENABLE_FILES_LEGACY_ROUTES` | `true` | Включить legacy-маршруты файлов. **Автоматически отключается в `production`.** |
| `MAX_REQUEST_BODY_BYTES` | `1048576` | Максимальный размер тела HTTP-запроса (байты). |
| `REQUEST_TIMEOUT_SECONDS` | `15.0` | Таймаут входящего HTTP-запроса (секунды). |
| `TRACE_HEADER_NAME` | `X-Correlation-Id` | Имя заголовка трассировки. |
| `IDEMPOTENCY_TTL_DAYS` | `30` | Время хранения ключей идемпотентности (дни). |

---

## Bootstrap

| Переменная | По умолчанию | Описание |
|---|---|---|
| `ADMIN_BOOTSTRAP` | `false` | Создать admin-пользователя при старте. |
| `ADMIN_EMAIL` | `admin@example.com` | Email admin-пользователя. |
| `ADMIN_PASSWORD` | `""` | Пароль admin-пользователя. |
| `ADMIN_TENANT` | `public` | Slug тенанта для admin-пользователя. |
| `DEMO_BOOTSTRAP` | `false` | Создать демо-данные при старте. |
| `DEMO_TENANT_ID` | `demo` | ID тенанта для демо-данных. |
| `DEMO_COMPANY_NAME` | `ООО Демо Строй` | Название демо-компании. |
| `DEMO_SITE_NAME` | `Площадка Север` | Название демо-площадки. |

---

## Интеграции

| Переменная | По умолчанию | Описание |
|---|---|---|
| `USE_1C_INTEGRATION` | `false` | Включить pilot-адаптер 1С. |
| `USE_EDO_INTEGRATION` | `false` | Включить ЭДО-интеграцию. |
| `USE_FRDO_INTEGRATION` | `false` | Включить pilot-адаптер ФРДО. |
| `USE_EISOT_INTEGRATION` | `false` | Включить pilot-адаптер ЕИСОТ. |
| `EDO_INTEGRATION_BASE_URL` | `null` | Base URL ЭДО-оператора. Если задан — используется `HttpEDOIntegration`, иначе `StubEDOIntegration`. |
| `EDO_INTEGRATION_API_TOKEN` | `null` | API-токен ЭДО-оператора. |
| `EDO_INTEGRATION_TIMEOUT_SECONDS` | `30.0` | Таймаут HTTP-запросов к ЭДО (секунды). |
| `EDO_INTEGRATION_OUTBOUND_PATH` | `/v1/outbound/documents` | Путь для отправки документов. |

---

## Производственные ограничения

В `staging` и `production` приложение **откажется запускаться**, если:

- `SECRET_KEY` равен `change-me`
- `POSTGRES_PASSWORD` равен `change_me`
- `S3_ACCESS_KEY` равен `prt_local_access`
- `S3_SECRET_KEY` равен `prt_local_secret`
- `S3_BACKEND` равен `memory`
- `INBOUND_WEBHOOK_HMAC_SECRET` пуст
- `PRIVATE_KEY_PEM` / `PUBLIC_KEY_PEM` не заданы или совпадают с дев-ключами

Кроме того, в `production`:
- `ENABLE_OPENAPI_DOCS` принудительно устанавливается в `false`
- `ENABLE_FILES_LEGACY_ROUTES` принудительно устанавливается в `false`
- `APP_CORS_ORIGINS="*"` запрещён при `APP_CORS_ALLOW_CREDENTIALS=true`
