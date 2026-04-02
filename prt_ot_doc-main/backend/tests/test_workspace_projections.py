from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import MappingProxyType, SimpleNamespace

import pytest
from sqlalchemy import Column, String, Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes.workspace import (
    role_workspace_summary,
    workspace_attention,
    workspace_task_inbox,
)
from app.core.security import AccessContext
from app.db.session import TenantBase
from app.models.models import ComplianceDeadline, OfflineSyncBatch
from app.models.obligations import Task, TaskPriority, TaskStatus


@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    if "tenant" not in TenantBase.metadata.tables:
        Table("tenant", TenantBase.metadata, Column("id", String(36), primary_key=True))
    async with engine.begin() as conn:
        await conn.run_sync(TenantBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def _access(user_id: str, role: str, tenant_id: str, tenant_slug: str) -> AccessContext:
    user = SimpleNamespace(
        id=user_id,
        email=f"{user_id}@tenant.test",
        role=SimpleNamespace(value=role),
        company_id=None,
    )
    return AccessContext(
        user=user,
        claims=MappingProxyType(
            {
                "sub": user_id,
                "tenant": tenant_slug,
                "tenant_id": tenant_id,
                "role": role,
                "roles": [role],
            }
        ),
        tenant_slug=tenant_slug,
        tenant_id=tenant_id,
        company_id=None,
    )


@pytest.mark.asyncio
async def test_workspace_attention_returns_overdue_deadlines_and_sync_counts(db_session) -> None:
    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    access = _access("user-1", "admin", tenant.id, tenant.slug)
    now = datetime.now(timezone.utc)

    db_session.add_all(
        [
            Task(
                tenant_id=tenant.id,
                title="Overdue task",
                status=TaskStatus.OPEN,
                priority=TaskPriority.HIGH,
                due_at=now - timedelta(days=1),
                assignee_id=access.user.id,
            ),
            ComplianceDeadline(
                tenant_id=tenant.id,
                entity_type="training",
                entity_id="tr-1",
                due_at=now - timedelta(hours=1),
                status="overdue",
            ),
            OfflineSyncBatch(
                tenant_id=tenant.id,
                user_id=access.user.id,
                device_id="d-1",
                entity_type="incident",
                status="failed",
                payload={"id": "1"},
                error_payload={"error": "conflict"},
            ),
        ]
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=access, limit=20)

    assert payload.summary.overdue_tasks == 1
    assert payload.summary.overdue_deadlines == 1
    assert payload.summary.failed_sync_batches == 1
    assert payload.summary.readiness_blockers >= 1
    assert payload.items
    assert any(blocker.code == "templates_not_ready" for blocker in payload.blockers)
    assert any("Resolve readiness blockers" in rec for rec in payload.recommendations)
    assert any("Resolve overdue tasks" in rec for rec in payload.recommendations)


@pytest.mark.asyncio
async def test_workspace_task_inbox_worker_sees_only_own_tasks(db_session) -> None:
    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    worker = _access("worker-1", "worker", tenant.id, tenant.slug)
    now = datetime.now(timezone.utc)

    db_session.add_all(
        [
            Task(
                tenant_id=tenant.id,
                title="Worker task",
                status=TaskStatus.OPEN,
                priority=TaskPriority.MEDIUM,
                due_at=now + timedelta(hours=6),
                assignee_id=worker.user.id,
            ),
            Task(
                tenant_id=tenant.id,
                title="Other task",
                status=TaskStatus.OPEN,
                priority=TaskPriority.MEDIUM,
                due_at=now + timedelta(hours=12),
                assignee_id="another-user",
            ),
        ]
    )
    await db_session.commit()

    payload = await workspace_task_inbox(
        tenant=tenant,
        session=db_session,
        access=worker,
        limit=50,
        offset=0,
    )

    assert payload.total == 1
    assert len(payload.items) == 1
    assert payload.items[0].title == "Worker task"


@pytest.mark.asyncio
async def test_role_workspace_summary_for_manager_scopes_to_assignee(db_session) -> None:
    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    manager = _access("manager-1", "line_manager", tenant.id, tenant.slug)
    now = datetime.now(timezone.utc)

    db_session.add_all(
        [
            Task(
                tenant_id=tenant.id,
                title="Own overdue task",
                status=TaskStatus.OPEN,
                priority=TaskPriority.HIGH,
                due_at=now - timedelta(hours=2),
                assignee_id=manager.user.id,
            ),
            Task(
                tenant_id=tenant.id,
                title="Other user task",
                status=TaskStatus.OPEN,
                priority=TaskPriority.MEDIUM,
                due_at=now + timedelta(hours=2),
                assignee_id="other-user",
            ),
        ]
    )
    await db_session.commit()

    payload = await role_workspace_summary(tenant=tenant, session=db_session, access=manager)

    assert payload.role == "line_manager"
    assert payload.open_tasks == 1
    assert payload.overdue_tasks == 1
    assert payload.open_incidents == 0
