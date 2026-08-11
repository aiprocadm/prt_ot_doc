from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import Column, String, Table, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import SharedBase, TenantBase
from app.domains.npa.impact import NpaImpactService
from app.models.models import NPABinding
from app.models.notifications import (
    NotificationChannel,
    NotificationTemplate,
    NotificationType,
    PlanTask,
    PlanTaskStatus,
)
from app.models.npa import NpaAct, NpaRevision
from app.modules.workflow.service import WorkflowService


@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    if "tenant" not in TenantBase.metadata.tables:
        Table("tenant", TenantBase.metadata, Column("id", String(36), primary_key=True))
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS public"))
        await conn.run_sync(SharedBase.metadata.create_all)
        await conn.run_sync(TenantBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def _valid_graph() -> dict[str, object]:
    return {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "approval", "type": "approval", "assignee_role_code": "admin"},
            {"id": "end", "type": "end"},
        ],
        "transitions": [
            {"from": "start", "to": "approval"},
            {"from": "approval", "to": "end"},
        ],
    }


@pytest.mark.asyncio
async def test_workflow_validation_rejects_unreachable_nodes(db_session) -> None:
    service = WorkflowService(db_session, "tenant-1")
    graph = _valid_graph()
    graph["nodes"].append({"id": "orphan", "type": "notification"})  # type: ignore[index]

    with pytest.raises(Exception) as exc:
        service.validate_graph(graph)

    assert "unreachable" in str(exc.value)


@pytest.mark.asyncio
async def test_npa_update_tasks_are_deduplicated_and_revision_aware(db_session) -> None:
    act = NpaAct(code="NPA-1", title="Act", edition="2026")
    db_session.add(act)
    await db_session.flush()
    revision = NpaRevision(act_id=act.id, revision_code="rev-1", title="Revision", effective_from=date(2026, 1, 1))
    db_session.add(revision)
    await db_session.flush()
    db_session.add(
        NPABinding(
            tenant_id="tenant-1",
            npa_id=act.id,
            entity_type="template_version",
            entity_id="tpl-1",
            context={"workflow_definition_id": "wf-1"},
            ref="binding-1",
        )
    )
    await db_session.flush()

    service = NpaImpactService(db_session, "tenant-1")
    first = await service.create_update_tasks(act.id, "user-1", revision_id=revision.id)
    second = await service.create_update_tasks(act.id, "user-1", revision_id=revision.id)

    assert len(first) == len(second) == 2
    rows = (await db_session.execute(select(PlanTask))).scalars().all()
    assert len(rows) == 2
    assert all(task.status == PlanTaskStatus.OPEN for task in rows)
    assert all(revision.id in (task.description or "") for task in rows)


@pytest.mark.asyncio
async def test_notification_template_persists(db_session) -> None:
    item = NotificationTemplate(
        tenant_id="tenant-1",
        code="approval-deadline",
        channel=NotificationChannel.INAPP,
        type=NotificationType.APPROVAL_DEADLINE,
        locale="ru",
        title_template="Срок согласования",
        body_template="Документ требует решения",
        variables_schema={"entity_id": "string"},
    )
    db_session.add(item)
    await db_session.flush()

    stored = await db_session.get(NotificationTemplate, item.id)
    assert stored is not None
    assert stored.code == "approval-deadline"
    assert stored.channel == NotificationChannel.INAPP
