# Backend_TZ.md
Версия: v1.0 • Дата: 15.10.2025 • Репозиторий: https://github.com/alexkarpov772/prt_ot_doc

## 0) Резюме
**Цель.** Бэкенд для платформы подготовки и сопровождения документов по ОТ/ПБ/ПромБез/Эко, СИЗ, проверок и обучения. REST API + очереди для генерации пакетов документов и отчетов.
**Ограничения.** Не ломать текущие публичные интерфейсы без миграций. Совместимость с существующими модулями в `app`. Мультиарендность обязательна.
**Диаграмма контекста (C4 System/Container, текст).**
Пользователи → Frontend → Backend API → (PostgreSQL, Redis, MinIO, File renderer, NPA registry). Внешние: 1С, ФРДО, ЕИСОТ.
```
+ Users
  -> Frontend (Web)
     -> Backend API (FastAPI)
        -> PostgreSQL (multi-tenant)
        -> Redis (tasks, cache)
        -> MinIO (files)
        -> LibreOffice/Pandoc (doc/pdf)
        -> NPA Registry (internal tables)
        -> Webhooks: 1C, FRDO, EISOT
```

## 1) Архитектура
**Выбор.** Монолит с модульной архитектурой внутри (FastAPI + SQLAlchemy + Celery). Причина: быстрее MVP, проще транзакции и общие миграции. Позже выделяем тяжелые домены (LMS, генерация отчётов) в сервисы.
**Компоненты.**
- API слой: `backend/app/api` (версии v1).
- Домены: `backend/app/domains/*` (templating, packs, replace, files, npa, sign, audit, billing).
- Модель/ORM: `backend/app/models`.
- Доступ к БД: `backend/app/db/session.py`.
- Очереди: `backend/app/tasks.py` + Celery worker.
**Потоки данных.**
Загрузка входных данных → валидация → доменная логика → БД → постановка задач генерации → готовые файлы в MinIO → ссылки в API.
**Асинхронность.** Celery + Redis: генерация документов, массовая рассылка, отчёты, импорт НПА.
**Масштабирование.** API — stateless, масштабируется горизонтально; Celery — по рабочим; PostgreSQL — вертикально/реплики read.

## 2) Хранение данных
**СУБД.** PostgreSQL 14+. Причина: транзакции, индексы, JSONB, FTS, схемы для мультиарендности.
**ERD.** см. `erd.puml`.
**Словарь данных (основное).**
- tenant(id, name, slug, created_at)
- user(id, tenant_id, email, hash, role, is_active, ...)
- company(id, tenant_id, name, inn, kpp, ogrn, legal_address, actual_address, director, bank_name, bank_bik, bank_account, phone_numbers, email, logo_file_id, stamp_file_id, work_types, hazardous_factors)
- site(id, tenant_id, company_id, name, address)
- position(id, tenant_id, company_id, name)
- person(id, tenant_id, company_id, fio, birth_date, position_id, personnel_number, hired_at, qualifications_json, snils, passport, current_ppe, email)
- training(id, tenant_id, person_id, program, issued_at, expires_at, cert_no)
- medical_exam(id, tenant_id, person_id, date, conclusion, expires_at)
- permit(id, tenant_id, person_id, type, issued_at, expires_at)
- ppe_item(id, tenant_id, name, norm_code, size, category)
- ppe_issue(id, tenant_id, person_id, item_name, issued_at, expires_at, status)
- template(id, tenant_id, code, title, version, storage_key, vars_schema)
- pack(id, tenant_id, code, title, description, version)
- pack_item(id, pack_id, template_id, order_no, required)
- document(id, tenant_id, company_id, person_id, template_id, status, storage_key, created_by)
- document_version(id, document_id, template_version, data_json, file_key, created_at)
- checklist(id, tenant_id, npa_code, title, version)
- inspection(id, tenant_id, site_id, checklist_id, started_at, finished_at, status)
- violation(id, tenant_id, inspection_id, clause_ref, severity, photo_key, description)
- corrective_action(id, tenant_id, violation_id, action, due_date, status)
- incident(id, tenant_id, site_id, occurred_at, severity, description, status)
- risk(id, tenant_id, company_id, site_id, hazard, probability, severity, level, controls)
- audit_log(id, tenant_id, actor_id, action, entity, entity_id, diff_json, created_at)
- file(id, tenant_id, storage_key, sha256, size, mime, meta_json)
- feature(id, code, title); feature_enablement(tenant_id, feature_id, on, config_json)
**Миграции.** Alembic. Нумерация YYYYMMDD_HHMM. Каждая миграция обратима. Тестовые данные через seed-скрипт.
**Архив/retention.** Документы и файлы: S3 версии + неизменяемые версии; retention 5 лет, затем архив в Glacier-совместимое хранилище (параметризуемо).

## 3) Бизнес-логика и инварианты
**Инварианты.**
- Все записи содержат tenant_id.
- Документ имеет хотя бы одну версию. Версии неизменяемы.
- Pack привязан к шаблонам по версиям. Нельзя удалить шаблон, если он в активном pack.
- PPE issue без person_id недопустим.
**Сценарии.**
### «Выход на объект»
1) Ввод: company, site, список persons. 2) Проверка: обучение, медосмотр, СИЗ. 3) Генерация pack `OT_ENTER_SITE`. 4) Документы → MinIO. 5) Статус pack-run OK/FAIL.
### «Несчастный случай»
1) Ввод: incident. 2) Чек-лист расследования. 3) Пакет актов и приказов. 4) Контроль корректирующих действий.
### Проверка ПБ/ОТ
1) Выбор checklist по НПА. 2) Ответы + фотофиксация. 3) Акт и предписание. 4) Контроль исполнений.

## 4) API контракт
Полный контракт в `openapi.yaml`. Единый стиль: пагинация `?limit=&offset=`, сортировка `?order=field:asc`. Ошибки с полями: `code`, `message`, `details`, `trace_id`. Идемпотентность: заголовок `Idempotency-Key`.
Примеры cURL:
```
curl -H "Authorization: Bearer TOKEN" -X POST https://host/api/v1/documents/generate   -H "Content-Type: application/json" -d '{"template_code":"OT_ORDER","company_id":"...","data":{}}'
```

## 5) Безопасность и доступ
**Аутентификация.** JWT (OAuth2 Password flow) с обновлением access через refresh. Причина: простая интеграция с фронтом и мобильными клиентами.
**Авторизация.** RBAC (+ ABAC по tenant_id и company_id). Политики на уровне эндпоинтов и записей.
**Валидация.** Pydantic-схемы. Ограничение входных размеров: JSON ≤ 1 MiB, файлы ≤ 20 MiB (конфигурируемо).
**Секреты.** .env + переменные окружения. Ротация ключей JWT через kid и таблицу активных ключей.
**Аудит.** Все изменения важных сущностей пишутся в audit_log.

## 6) Файлы и шаблоны
**Хранилище.** MinIO S3. Ключ: `tenants/{{tenant}}/{{yyyy}}/{{mm}}/{{sha256}}.{{ext}}`.
**Типы.** DOCX, PDF, XLSX, CSV, JPEG/PNG. Скан на тип/миме, sha256, размер.
**Рендер.** DOCX-шаблоны (docxtpl/jinja). Колонтитулы и логотипы — параметры шаблона. Массовая генерация — Celery батчи. Версионирование шаблонов обязательно.

## 7) Ошибки, логирование, метрики
**Формат ошибок.** JSON: `{{"code":"validation_error","message":"...","details":{{}},"trace_id":"..."}}`.
**Логи.** Структурированные (JSONLines). Маскирование PII. Корреляция по trace_id.
**Метрики.** /health, /ready. Экспорт Prometheus `/metrics` при ENABLE_METRICS=1.

## 8) Нефункциональные требования
p95 latency ≤ 300 мс для простых GET, ≤ 3 с для генерации (асинхронно). Доступность ≥ 99.5%. Локализация: ru-RU по умолчанию; таймзона Europe/Moscow по конфигу.

## 9) Тестирование
Unit: доменная логика; Integration: БД + MinIO + Redis через testcontainers; E2E: ключевые флоу. Покрытие критической логики ≥ 80%. Контрактные тесты из `openapi.yaml` через schemathesis.

## 10) DevEx, сборка и запуск
Структура: уже существующая `app`. Фиксируем версии зависимостей в requirements*. Dockerfile и compose присутствуют. Добавить `Makefile` с целями: `make up`, `make down`, `make test`, `make lint`, `make migrate`.
Pre-commit: black, ruff, mypy, detect-secrets. CI: lint → tests → build → publish артефактов (`openapi.yaml`, `erd.puml`) в релизы.

## 11) Миграция существующего кода
- Переиспользовать: фабрика приложения, настройки, сессии БД, доменные скелеты.
- Рефакторить: domains/* реализация, модели довести до ERD, API v1 довести до контракта.
- Совместимость: не менять публичные пути без alias и депрекейта. Миграции Alembic по шагам.

## 12) План работ
Эпики (MoSCoW):
- MUST: Auth/RBAC, Tenants, Companies/Persons, Templates/Docs, Packs, Files, Tasks.
- SHOULD: Checklists/Inspections, PPE, Incidents, Risks, AuditLog.
- COULD: Billing, NPA registry v1, FRDO/1C webhooks.
- WON'T (в этом релизе): LMS полноценная.
Инкременты: MVP (8 недель) → Beta (+6 недель) → Prod (+4 недели).

## 13) Приложения
- См. `openapi.yaml`, `erd.puml`.
