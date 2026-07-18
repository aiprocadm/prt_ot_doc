from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status

from app.models.models import RoleEnum
from app.models.obligations import Task, TaskStatus
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_list_and_close_obligations(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        overdue = Task(
            tenant_id=str(tenant.id),
            title="Close CAPA",
            entity_type="corrective_action",
            entity_id="ca-1",
            due_at=datetime.now(timezone.utc) - timedelta(days=1),
            status=TaskStatus.OPEN,
        )
        session.add(overdue)
        await session.commit()
        task_id = overdue.id

    headers = await make_auth_headers(RoleEnum.ADMIN)
    list_response = await async_client.get("/api/v1/obligations?overdue=true", headers=headers)
    assert list_response.status_code == status.HTTP_200_OK
    items = list_response.json()
    assert any(item["id"] == task_id for item in items)

    patch_response = await async_client.patch(f"/api/v1/obligations/{task_id}", headers=headers)
    assert patch_response.status_code == status.HTTP_200_OK
    assert patch_response.json()["status"] == "done"
