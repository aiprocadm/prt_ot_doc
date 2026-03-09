# CODEX_HANDOFF_NEXT

## Что это за проект
B2B SaaS-платформа по ОТ/ПБ/документным pipeline/обучению/СИЗ/рискам/инцидентам с multi-tenant изоляцией и клиентским порталом.

## Фактическое состояние
- Backend и frontend функционально широкие; ключевые домены и API уже присутствуют.
- Tenant/RBAC/Idempotency/Audit/Outbox реализованы, но покрытие и стабильность отдельных сценариев неоднородны.
- В этом проходе добавлен context pack + traceability + hardening правка tenant-scope для изменения квот.

## Ключевые модули
- API aggregation: `backend/app/api/v1/router.py`.
- Tenant guard: `backend/app/middleware/tenant.py`, `backend/app/api/dependencies.py`.
- Tenants management: `backend/app/api/routes/tenants.py`.
- Frontend routes/guards: `frontend/src/router/AppRouter.tsx`, `ProtectedRoute.tsx`.

## Что критично по ТЗ
1. Невозможность кросс-tenant доступа.
2. Явные RBAC/ABAC ограничения.
3. Идемпотентность state-changing endpoint.
4. Аудит критичных изменений.
5. Безопасность файлов и экспортов.

## Что найдено в этом проходе
- Потенциальная tenant-scope дыра в `PATCH /tenants/{tenant_id}/quotas`: отсутствовала жёсткая сверка `tenant_id` из path и текущего tenant context.
- Нестабильный idempotency кейс в packs run тесте (500) — зафиксировано как критический remaining gap для следующего шага.

## Что исправлено
- Добавлен tenant scope check в `patch_tenant_quotas_endpoint` и `admin`-обёртку.
- Добавлен тест на запрет изменения квот чужого tenant.
- Добавлены документы: context pack, traceability matrix, runbook, limitations, final gaps.
- Добавлена единая команда `make codex-audit`.

## Что осталось сделать
1. Разобрать и починить `packs/run` idempotency 500 кейс (см. `tests/test_idempotency.py::test_pack_run_idempotency`).
2. Усилить матрицу permission tests (admin/client/auditor/specialist).
3. Закрыть search/export leakage regression suite.
4. Доработать backup/restore drills + observability SLO checks.

## Рекомендуемый порядок продолжения
1. Стабилизировать packs idempotency.
2. Допройти security/tenant leakage regression на files/search/export.
3. Расширить ABAC test matrix.
4. Перепроверить pilot readiness с `make codex-audit` + `make final-acceptance`.

## Команды
- Быстрый аудит: `make codex-audit`
- Критичные тесты: `python -m pytest tests/test_tenant_header_required.py tests/test_tenant_security.py tests/test_webhooks_dispatch.py -q`
- Полная приемка (если окружение готово): `make final-acceptance`

## Что смотреть в первую очередь
1. `docs/FINAL_CRITICAL_GAPS.md`
2. `docs/SPEC_TRACEABILITY_MATRIX.md`
3. failing tests в блоке idempotency/packs
