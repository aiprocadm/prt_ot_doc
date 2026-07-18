# P1 Compliance Report

> **DEPRECATED (2026-05-04).** Замкнутый отчёт прошлой волны. Текущий статус P0/P1 — в `docs/audit/TZ_COVERAGE_MATRIX.md` и `AI_IMPLEMENTATION_REPORT.md`. Кандидат на удаление в Wave 4 (см. `docs/CLEANUP_CANDIDATES.md`).

## Summary
This report documents the P1 compliance work for RBAC/ABAC, roles, core entities, obligations/tasks, and WS scope.

## Checklist
- [x] Expand RoleEnum + role assignment APIs (`/api/v1/admin/users/{id}/roles`).
- [x] ABAC attributes for site/document/status/risk_level enforced in security helpers.
- [x] Core entities: department, contract, order, invoice with tenant-scoped CRUD.
- [x] Deadlines/obligations engine: task model, reminders worker, auto-creation from training + medical requirement.
- [x] WS decision: stub endpoint `/ws/v1/events` with 501 and docs note.
- [x] Tests added for RBAC/ABAC, roles, finance CRUD, obligations, reminders, WS stub.

## Files changed
- Backend models: `backend/app/models/models.py`, `backend/app/models/finance.py`, `backend/app/models/obligations.py`, `backend/app/models/document.py`.
- Backend services: `backend/app/services/obligations.py`, `backend/app/services/events.py`, `backend/app/services/outbox.py`, `backend/app/tasks.py`.
- Backend API: `backend/app/api/routes/admin_users.py`, `departments.py`, `contracts.py`, `orders.py`, `invoices.py`, `medical.py`, `tasks.py`, `ws_stub.py`.
- Migrations: `backend/app/migrations/versions/20250410_p1_entities_tasks_roles.py`.
- Frontend tasks UI: `frontend/src/features/tasks/TaskTable.tsx`, `frontend/src/types/dto/tasks.ts`.
- Docs: `docs/ARCHITECTURE.md`, `docs/spec/mapping.md`, `docs/runbook.md`.

## How to verify
1. Apply migrations.
2. Start backend, celery workers, and beat.
3. Run tests: `pytest`.

## Deferred (P2)
- Full WebSocket event streaming (replaced with HTTP 501 stub at `/ws/v1/events`).
