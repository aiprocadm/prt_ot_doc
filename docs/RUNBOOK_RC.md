# RUNBOOK RC

## 1) Поднятие проекта (локально)
```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
npm --prefix frontend ci
```

## 2) Базовые проверки backend
```bash
python -m compileall -q backend/app
PYTHONPATH=backend python scripts/contract/validate.py
```

## 3) Проверки CI-стабильности frontend
```bash
npm --prefix frontend run ci
```

## 4) Smoke health/readiness (локально)
```bash
PYTHONPATH=backend APP_ENV=test uvicorn app.main:app --host 127.0.0.1 --port 18000
# В отдельном терминале:
curl -fsS http://127.0.0.1:18000/healthz
curl -i http://127.0.0.1:18000/readyz
```

Ожидание:
- `healthz` должен быть `200`.
- `readyz` будет `503`, если не подняты Postgres/Redis (это нормально для локального «без инфраструктуры» прогона).

## 5) Полный smoke в инфраструктурном окружении
```bash
docker compose up -d --build
make smoke
```

## 6) Что проверить перед релизом
1. Tenant guard (`X-Tenant`) и idempotency smoke.
2. Job status transitions (queued/running/success/error/canceled).
3. Сквозные UI-потоки: шаблоны, пакеты, задания, клиентский кабинет.
4. Обновленные RC-документы:
   - `docs/RELEASE_CANDIDATE_AUDIT.md`
   - `docs/ACCEPTANCE_CHECKLIST.md`
   - `docs/CI_STABILIZATION_REPORT.md`
   - `docs/KNOWN_LIMITATIONS_RC.md`
