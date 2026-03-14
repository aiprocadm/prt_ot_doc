# RUNBOOK RC

## 1) Поднять проект
```bash
cp .env.example .env
make cs:dev
```

## 2) Базовые проверки RC
```bash
./scripts/codex_audit.sh
pytest -q tests/test_inbound_webhook_tenant_context.py
pytest -q tests/test_tenant_header_required.py tests/test_idempotency.py tests/integration/test_job_status_flow.py
npm --prefix frontend run build
```

## 3) Smoke-тестирование
```bash
# важно: backend уже должен слушать localhost:8000
./scripts/smoke.sh
```

## 4) Локальная проверка webhook ingress
```bash
# inbound webhook (без X-Tenant)
curl -X POST http://localhost:8000/api/v1/webhooks/inbound/edo \
  -H 'Content-Type: application/json' \
  -d '{"event_id":"evt-local","external_id":"ext-local","status":"accepted"}'

# EDO webhook (без X-Tenant)
curl -X POST http://localhost:8000/api/v1/edo/webhooks/mock \
  -H 'Content-Type: application/json' \
  -d '{"event_id":"evt-edo","external_id":"ext-edo","status":"accepted","raw_payload":{}}'
```

## 5) Перед релизом (рекомендуется)
```bash
pytest -q
make lint
```
