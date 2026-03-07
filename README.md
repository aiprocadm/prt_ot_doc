# prt-ot-doc

Платформа управления документами и процессами ОТ/ПБ/ПромБез: FastAPI backend, React/Vite frontend, dockerless-режим для Codespaces и docker-compose для полного локального контура.

## Quick start (Codespaces)
```bash
make cs:reset
cp .env.example .env
# в .env задайте ADMIN_BOOTSTRAP=1, DEMO_BOOTSTRAP=1 и ADMIN_EMAIL/ADMIN_PASSWORD/ADMIN_TENANT
make cs:dev
make cs:test
```

После старта:
- Frontend: `http://localhost:5173`
- Backend health: `http://localhost:8000/health`
- Ready probe: `http://localhost:8000/readyz`

## Dev login (без секретов в git)
Используйте значения **из локального `.env`**:
```env
ADMIN_BOOTSTRAP=1
ADMIN_EMAIL=admin@example.local
ADMIN_PASSWORD=ChangeMe123!
ADMIN_TENANT=demo
```

Bootstrap админа активен только для `APP_ENV=development|test`.

## Tests
```bash
make cs:test
./scripts/pytest.sh --collect-only -q
npm --prefix frontend test
```

## Source of truth
- Единое полное ТЗ: [docs/spec/TZ_FULL_UNIFIED.md](docs/spec/TZ_FULL_UNIFIED.md)
- Матрица покрытия ТЗ: [docs/audit/TZ_COVERAGE_MATRIX.md](docs/audit/TZ_COVERAGE_MATRIX.md)
- Baseline verification: [docs/audit/BASELINE_VERIFICATION.md](docs/audit/BASELINE_VERIFICATION.md)
- Runbook для Codespaces: [docs/runbook-codespaces.md](docs/runbook-codespaces.md)
- Demo walkthrough: [docs/runbook/DEMO_WALKTHROUGH.md](docs/runbook/DEMO_WALKTHROUGH.md)
- Гайд по тестам: [docs/testing.md](docs/testing.md)

## Multi-tenant bootstrap
- Все бизнес-эндпойнты требуют заголовок `X-Tenant`.
- Создать tenant:
```bash
python scripts/create_tenant.py <slug> "Tenant Name" owner@example.com
```
- Подготовить tenant-schema:
```bash
python scripts/migrate_tenant.py <slug>
```
- Тесты tenancy:
```bash
pytest -q tests/test_tenancy_enforcement.py
```


## Templates module quickstart

- Create template card: `POST /api/v1/templates/catalog` with JSON `{ "code": "safety_order", "name": "Safety order" }`.
- Upload DOCX version: `POST /api/v1/templates/{template_id}/versions:upload` (`multipart/form-data`, field `file`, optional `Idempotency-Key`).
- Run linter: `POST /api/v1/templates/{template_id}/versions/{version_id}:lint`.
- Render preview: `POST /api/v1/templates/{template_id}/versions/{version_id}:preview` with JSON data payload.

## Approval → Sign → EDO flow (dev, mock adapters)

Минимальный сквозной сценарий для локальной проверки (mock providers):

1. Создать маршрут согласования:
   - `POST /api/v1/approval-routes`
   - затем шаги `POST /api/v1/approval-routes/{id}/steps`.
2. Запустить согласование для `document` или `pack`:
   - `POST /api/v1/approvals/start`.
3. Принять решение на шаге:
   - `POST /api/v1/approvals/{id}/approve|reject|delegate|comment`.
4. Запросить подпись:
   - `POST /api/v1/sign/requests` c `provider_code=mock`.
5. Обновить статус/верифицировать подпись:
   - `POST /api/v1/sign/requests/{id}/refresh-status`
   - `POST /api/v1/sign/requests/{id}/verify`.
6. Отправить сущность в ЭДО:
   - `POST /api/v1/edo/messages` c `operator_code=mock_edo`.
7. Обновить статус ЭДО вручную или вебхуком:
   - `POST /api/v1/edo/messages/{id}/refresh-status`
   - `POST /api/v1/webhooks/edo/{operator_code}`.

Все запросы к бизнес-эндпойнтам должны включать `X-Tenant`.

## Safety Core dev flow (employee → risk map → PPE → pack summary)

1. Создайте сотрудника и орг-контекст через существующие CRUD:
   - `POST /api/v1/companies`
   - `POST /api/v1/sites`
   - `POST /api/v1/positions`
   - `POST /api/v1/persons`
2. Создайте методику риска (`matrix` или `fine_kinney`) и активируйте её.
3. Добавьте hazards и bindings к `position/workplace/site`.
4. Постройте risk map для `person/workplace/site` в режиме `auto_from_binding` и выполните recalculate.
5. Создайте PPE catalog и PPE norms (scope: `position/workplace/hazard`).
6. Оформите `issue/return/replacement` в PPE журнале.
7. Проверьте personal card: required/issued/missing/expiring.
8. Для пакета «Выход на объект» запросите safety-сводку и используйте данные в шаблонах/контексте рендера.

> Везде обязателен `X-Tenant`; без него API отвечает `400`.
