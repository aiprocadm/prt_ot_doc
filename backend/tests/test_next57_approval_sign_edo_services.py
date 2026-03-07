from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import Column, String, Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import TenantBase
from app.models.models import (
    ApprovalInstance,
    ApprovalInstanceStep,
    ApprovalInstanceStepStatus,
    ApprovalRoute,
    ApprovalRouteStep,
    ApprovalRouteStatus,
)
from app.modules.approvals.service import ApprovalDecisionService, ApprovalInstanceService, ApprovalRouteService, EscalationService


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


@pytest.mark.asyncio
async def test_route_resolution_matches_conditions_and_default(db_session) -> None:
    tenant_id = "tenant-1"
    matching = ApprovalRoute(
        tenant_id=tenant_id,
        code="doc-hi",
        name="Doc High",
        status=ApprovalRouteStatus.ACTIVE,
        applies_to="document",
        conditions_json={"document_type": ["incident_act"], "amount_gte": 1000},
    )
    fallback = ApprovalRoute(
        tenant_id=tenant_id,
        code="default",
        name="Default",
        status=ApprovalRouteStatus.ACTIVE,
        applies_to="both",
        is_default=True,
        conditions_json={},
    )
    db_session.add_all([matching, fallback])
    await db_session.flush()

    service = ApprovalRouteService(db_session, tenant_id)
    selected = await service.resolve_route(
        applies_to="document",
        context={"document_type": "incident_act", "amount": 2500},
    )
    assert selected is not None
    assert selected.id == matching.id

    defaulted = await service.resolve_route(applies_to="pack", context={"document_type": "unknown"})
    assert defaulted is not None
    assert defaulted.id == fallback.id


@pytest.mark.asyncio
async def test_delegate_keeps_step_pending_with_new_assignee(db_session) -> None:
    tenant_id = "tenant-1"
    route = ApprovalRoute(
        tenant_id=tenant_id,
        code="route-1",
        name="R1",
        status=ApprovalRouteStatus.ACTIVE,
        applies_to="document",
        conditions_json={},
    )
    db_session.add(route)
    await db_session.flush()
    step = ApprovalRouteStep(
        tenant_id=tenant_id,
        approval_route_id=route.id,
        order_no=1,
        user_id="user-a",
        step_type="approve",
    )
    db_session.add(step)
    await db_session.flush()

    instance = await ApprovalInstanceService(db_session, tenant_id).start(
        entity_type="document",
        entity_id="doc-1",
        approval_route_id=route.id,
        started_by="starter",
    )

    decided = await ApprovalDecisionService(db_session, tenant_id).decide(
        instance_id=instance.id,
        actor_user_id="user-a",
        decision="delegate",
        target_user_id="user-b",
        comment="handover",
    )
    assert decided.id == instance.id

    instance_step = (
        await db_session.execute(
            select(ApprovalInstanceStep).where(ApprovalInstanceStep.approval_instance_id == instance.id)
        )
    ).scalar_one()
    assert instance_step.status == ApprovalInstanceStepStatus.PENDING
    assert instance_step.assignee_user_id == "user-b"
    assert instance_step.delegated_from_user_id == "user-a"


@pytest.mark.asyncio
async def test_escalation_reassigns_overdue_step(db_session) -> None:
    tenant_id = "tenant-1"
    route = ApprovalRoute(
        tenant_id=tenant_id,
        code="route-2",
        name="R2",
        status=ApprovalRouteStatus.ACTIVE,
        applies_to="document",
        conditions_json={},
    )
    db_session.add(route)
    await db_session.flush()
    route_step = ApprovalRouteStep(
        tenant_id=tenant_id,
        approval_route_id=route.id,
        order_no=1,
        user_id="user-a",
        step_type="approve",
        escalation_user_id="user-escalated",
    )
    db_session.add(route_step)
    await db_session.flush()

    instance = ApprovalInstance(
        tenant_id=tenant_id,
        entity_type="document",
        entity_id="doc-2",
        approval_route_id=route.id,
        status="running",
        started_by="starter",
        current_step_no=1,
    )
    db_session.add(instance)
    await db_session.flush()

    instance_step = ApprovalInstanceStep(
        tenant_id=tenant_id,
        approval_instance_id=instance.id,
        route_step_id=route_step.id,
        order_no=1,
        assignee_user_id="user-a",
        status=ApprovalInstanceStepStatus.PENDING,
        due_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),
    )
    db_session.add(instance_step)
    await db_session.flush()

    changed = await EscalationService(db_session, tenant_id).escalate_overdue()
    assert changed == 1
    assert instance_step.assignee_user_id == "user-escalated"
    assert instance_step.delegated_from_user_id == "user-a"
