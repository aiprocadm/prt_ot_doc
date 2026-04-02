# FINAL PERFORMANCE / RELIABILITY REPORT

Дата: 2026-03-09

## Environment assumptions
- Local dev container, SQLite test DB, in-process ASGI tests.
- Не является production-like perf стендом.
- Численные SLA результаты ниже отмечены как baseline/non-prod.

## Verification scope
1. API latency baseline (functional proxy via pytest critical suites)
2. Render/PDF conversion correctness and stability
3. Replace batch behavior (functional)
4. Webhook/outbox reliability (retry/idempotency)
5. Search/indexing functional lag checks
6. Export queue functional completion

## Measured values (current run)
| Check | Target | Measured | Pass/Fail | Notes |
|---|---:|---:|---|---|
| Key read APIs p95 | <=1s | N/A in this run | WARN | Нужен k6/locust against stage (в final-acceptance пока функциональный proxy) |
| 30 DOCX->PDF <=60s | <=60s | N/A in this run | WARN | Есть unit/integration correctness, нет stress profile |
| Replace 500 files <=3m | <=180s | N/A | WARN | Batch perf profile отсутствует |
| EDO/webhook propagation <=60s | <=60s | Functional pass | PASS* | Проверка функциональная, не load SLA; контракт/доставка проходят final-acceptance |
| Search indexing lag | acceptable | Functional pass | PASS* | Имеются indexing tests |
| Export queue completion | acceptable | Functional pass | PASS* | Покрыто api/integration тестами |

## Bottlenecks observed / expected
- PDF throughput ограничен worker/LibreOffice pool size.
- Replace performance зависит от DOCX complexity + I/O storage latency.
- Webhook latency зависит от retry policy и receiver availability.

## Recommended tuning
1. Вынести perf profile в `scripts/perf/` + k6 сценарии для key APIs.
2. Задать prod-like worker pool для render/pdf and queue concurrency.
3. Включить stage synthetic webhook receiver для SLA измерений.
4. Добавить scheduled perf trend report (p50/p95/p99).

## Reliability verification
- Idempotency replay/conflict test coverage: present.
- Outbox retry/dedup coverage: present.
- Health/readiness checks: present.
- Poison queue / cancel semantics: partial, needs dedicated final scenarios.


## Final acceptance gate snapshot
- `artifacts/final_acceptance/summary.json`: overall_status = `pass`.
- Migrations sanity (`alembic heads`) переведён из WARN в PASS после правки revision links.
- Backend/frontend/e2e/openapi/health/schema checks: PASS в последнем прогоне.
