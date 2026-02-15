# TZ_COMPLIANCE

Статусы: **OK / Partial**. Приоритеты: **P0/P1/P2**.

| Область | Статус | Priority | Примечание |
|---|---|---|---|
| DevX: open → run в Codespaces | OK | P0 | `make cs:dev` поднимает backend+frontend, `npm ci` встроен. |
| Tests discovery (CLI + VS Code) | OK | P0 | Дефолты переведены на in-memory/local; добавлен `scripts/pytest.sh`. |
| Dev login/bootstrap без секретов | OK | P0 | `ADMIN_*` из `.env`, bootstrap вызывается в lifespan. |
| Tenant guardrails (`X-Tenant` required) | OK | P0 | Middleware + тесты `tenant_required`. |
| KPI-1 Idempotency generate | OK | P0 | `tests/test_idempotency.py`. |
| KPI-2 tenant_required | OK | P0 | `tests/test_tenant_header_required.py`. |
| KPI-3 template delete guard 409 | OK | P0 | `tests/test_template_delete.py`. |
| KPI-4 outbox→webhook (dev mock) | Partial | P1 | Поведение покрыто функционально, явный SLA ≤60s стоит усилить отдельным time-bound тестом. |
| KPI-5 deterministic risk output | OK | P0 | `tests/test_risk_assessment_kpi5.py`. |
| Frontend newbie robustness | OK | P1 | Есть tenant gate, обработка `TENANT_REQUIRED`, smoke-тесты app/login/API client. |
| Repo hygiene | Partial | P2 | `.env.pilot.example` перенесён в `docs/examples`; `proxy/` и migration compose отмечены как optional в документации. |
