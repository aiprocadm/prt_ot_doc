# ARCHITECTURE

> **Канонические источники:**
>
> - **ТЗ (точка входа «по ТЗ»):** [`docs/spec/TZ_FULL_UNIFIED.md`](./spec/TZ_FULL_UNIFIED.md). Раздел A — MVP, B — полный объём, E — правила доработки (vNext §36).
> - **Полная архитектурная рамка vNext:** [`docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md`](./spec/PLATFORM_VNEXT_UPGRADE_SPEC.md), разделы:
>   - §28 — Backend-архитектура (стек, стиль, bounded contexts, расширяемость);
>   - §29 — Frontend-архитектура;
>   - §30 — API, интеграции, импорт;
>   - §31 — надёжность, очереди, self-healing, observability, backup/DR;
>   - §32 — безопасность и соответствие;
>   - §36 — обязательные ограничения для доработок.
> - **Целевая структура архитектуры (рабочее описание):** [`docs/spec/PLATFORM_DESIGN.md`](./spec/PLATFORM_DESIGN.md).
> - **Сжатые программные правила:** `backend/app/core/product_spec.py` (`ARCHITECTURE_RULES`, `ENGINEERING_RULES`, `PRODUCT_UX_RULES`, `SIX_QUESTIONS`).
>
> Этот файл — короткая навигация по архитектуре, а не дублирование требований.

## Platform shape

- **Style:** modular monolith (backend) + feature-sliced SPA (frontend); см. vNext §28.2 / §29.
- **Backend:** Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2.x + Alembic + Celery + Redis + PostgreSQL + MinIO/S3 + LibreOffice headless + ClamAV + Prometheus + OpenTelemetry (vNext §28.1).
- **Frontend:** React 18 + TypeScript strict + Vite + React Router + TanStack Query + Zustand + RHF + Zod + design system + PWA (vNext §29.1).
- **Cross-cutting concerns:** мульти-арендность (X-Tenant + schema-per-tenant), RBAC + ABAC + module-level access, immutable audit, idempotency, outbox/webhooks, async jobs, structured errors, correlation-id (см. канон §A.2 + vNext §31, §32).

## Canonical backend layering

| Слой | Назначение | Пути |
|------|-----------|------|
| `api/` | HTTP composition, route contracts, validation | `backend/app/api/{app.py,main.py,v1/router.py,routes/*}` |
| `modules/` | продуктовые модули и bounded contexts (целевой слой) | `backend/app/modules/*` (см. `docs/MODULES.md`) |
| `domains/` | легаси-домены (постепенно поглощаются `modules/`) | `backend/app/domains/*` |
| `services/` | orchestration / use-cases / межмодульная склейка | `backend/app/services/*` |
| `models/`, `schemas/`, `db/` | persistence + контракты | `backend/app/{models,schemas,db}/*` |
| `tasks/`, `worker.py` | async / Celery | `backend/app/tasks/*`, `backend/app/worker.py` |
| `migrations/` | Alembic | `backend/app/migrations/versions/*` |

## Document core (vNext §6)

1. Выбор `(template_code, version)` — vNext §6.2, канон §A.2.5.
2. Branding profile резолвится через tenant → company → site наследование — vNext §6.3.
3. Effective branch display name + header/footer requisites + watermark + preset собираются в стабильный header context.
4. Layout preset резолвится, плейсхолдеры рендерятся.
5. Preview возвращает reproducibility metadata и `apply_headers_payload`.
6. Сгенерированный DOCX уходит в async header application.
7. Pipeline продолжает: replace → PDF → approvals → sign → archive → EDO/portal — vNext §6.5.

KPI и приёмка — vNext §35.2 + канон §A.2.4 / §A.2.8 / §A.2.9 / §A.2.10.

## Frontend architecture

- **Feature-Sliced Design:** `frontend/src/{features,entities,widgets,pages,shared}/*` + `frontend/src/router/{AppRouter,pageRegistry,routeGroups}.tsx`.
- **API client:** `frontend/src/api/*` — автоматически инжектит `X-Tenant`.
- **State:** Zustand stores (`frontend/src/stores/*`) + TanStack Query.
- **Permissions:** `frontend/src/permissions/*` + компонент `<Can />`.
- **Tenant UX:** controlled `tenant_required`-flow без white-screen.
- Полная инвентаризация экранов — `docs/FRONTEND_SCREENS_INVENTORY.md` (82+ экранов, F1..F4 канона).

## Текущие архитектурные seams

- `backend/app/api/v1/route_groups.py` — единая регистрация роутеров (vs sprawl).
- `backend/app/models/{document_core,tenanting,ppe_registry}.py` — постепенная декомпозиция `app.models.models` без слома контрактов.
- `frontend/src/router/{pageRegistry,routeGroups,features}.tsx` — lazy-страницы и permission-aware кластеры.
- Operational frontend pages используют real tenant-scoped backend projections (а не showcase-arrays).

## Правила доработки (vNext §36)

См. раздел E в [`TZ_FULL_UNIFIED.md`](./spec/TZ_FULL_UNIFIED.md):

1. Не ломать существующие модули; не удалять API без слоя совместимости; новое — через feature flags; миграции — additive; tenant isolation; не смешивать bounded contexts напрямую; тяжёлое — в async workers.
2. Unit/integration/e2e тесты + OpenAPI + changelog + seed/demo + correlation-id + строгая типизация.
3. Новый экран — только с primary user goal; новая сущность — только с привязкой к existing master data; массовые операции — preview/прогресс/rollback; mobile/field — offline-aware.
4. Six questions to each new feature: для какой роли / в каком сценарии / какие данные / при сбое сети / как пользователь понимает / как отключается per-tenant.
