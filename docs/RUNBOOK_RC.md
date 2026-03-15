# RUNBOOK RC

## 1) Поднять окружение
```bash
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cd frontend && npm ci && cd ..
```

## 2) Критичный backend gate
```bash
./scripts/pytest.sh tests/test_tenant_header_required.py tests/test_idempotency.py tests/test_template_delete.py tests/test_health_ready.py
```

## 3) Frontend gate
```bash
cd frontend && npm run lint
cd frontend && npm run test -- --run
cd frontend && npm run build
```

## 4) Smoke (RC)
```bash
# Скрипт поддерживает dockerless авто-подъем API (AUTO_START_API=1 по умолчанию)
./scripts/smoke.sh
```
Если smoke в dockerless режиме сталкивается с известной несовместимостью SQLite/JSONB в Alembic, скрипт автоматически переключится в fallback smoke-gate (health + tenant enforcement), это ожидаемое RC-поведение (см. `docs/KNOWN_LIMITATIONS_RC.md`).

## 5) Финальная локальная проверка перед релизом
```bash
./scripts/final_acceptance.sh
```
