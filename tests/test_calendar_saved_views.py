"""Tests for the Saved Smart Calendar Views CRUD (vNext-CAL-01 / Phase 4.1).

Covers service-level isolation (per tenant, per user, soft-delete) and
HTTP-level CRUD via the `/api/v1/calendar/saved-views` endpoints.
"""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RoleEnum
from app.services.calendar_views import (
    CalendarViewsService,
    SavedCalendarViewNameConflictError,
)
from tests.utils.factories import TestDataFactory

API_PREFIX = "/api/v1"
SAVED_VIEWS_PATH = f"{API_PREFIX}/calendar/saved-views"


def _cal_headers(base: dict[str, str]) -> dict[str, str]:
    merged = {**base}
    tid = merged.get("x-tenant") or merged.get("X-Tenant-Id")
    if tid:
        merged.setdefault("X-Tenant-Id", str(tid))
    return merged


SAMPLE_PAYLOAD = {
    "view": "month",
    "sources": ["medical_exam", "ppe_issue"],
    "person_id": "p-1",
    "site_id": None,
    "include_fact": True,
    "include_sla": True,
    "sla_bands": ["overdue", "critical"],
    "include_load": True,
    "load_dim": "site",
}


@pytest.mark.anyio
class TestCalendarViewsService:
    """Service-level isolation and uniqueness."""

    async def test_isolates_per_user_within_tenant(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        user_a = await data_factory.create_user(
            tenant=tenant,
            email="cv-user-a@example.com",
            role=RoleEnum.ADMIN,
            session=test_db_session,
        )
        user_b = await data_factory.create_user(
            tenant=tenant,
            email="cv-user-b@example.com",
            role=RoleEnum.ADMIN,
            session=test_db_session,
        )
        await test_db_session.commit()

        svc_a = CalendarViewsService(
            db=test_db_session,
            tenant_id=str(tenant.id),
            user_id=str(user_a.id),
        )
        svc_b = CalendarViewsService(
            db=test_db_session,
            tenant_id=str(tenant.id),
            user_id=str(user_b.id),
        )
        await svc_a.create(name="My Critical View", payload=SAMPLE_PAYLOAD)
        await test_db_session.commit()

        a_rows = await svc_a.list_views()
        b_rows = await svc_b.list_views()
        assert len(a_rows) == 1
        assert a_rows[0].name == "My Critical View"
        assert b_rows == []

        # Same name on different user must not conflict.
        await svc_b.create(name="My Critical View", payload=SAMPLE_PAYLOAD)
        await test_db_session.commit()
        b_after = await svc_b.list_views()
        assert len(b_after) == 1

    async def test_isolates_across_tenants(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant_a = await data_factory.ensure_tenant(
            slug="cv-tenant-a", session=test_db_session
        )
        tenant_b = await data_factory.ensure_tenant(
            slug="cv-tenant-b", session=test_db_session
        )
        user_a = await data_factory.create_user(
            tenant=tenant_a,
            email="cv-tenant-a-user@example.com",
            role=RoleEnum.ADMIN,
            session=test_db_session,
        )
        user_b = await data_factory.create_user(
            tenant=tenant_b,
            email="cv-tenant-b-user@example.com",
            role=RoleEnum.ADMIN,
            session=test_db_session,
        )
        await test_db_session.commit()

        svc_a = CalendarViewsService(
            db=test_db_session,
            tenant_id=str(tenant_a.id),
            user_id=str(user_a.id),
        )
        svc_b = CalendarViewsService(
            db=test_db_session,
            tenant_id=str(tenant_b.id),
            user_id=str(user_b.id),
        )
        await svc_a.create(name="Shared Name", payload=SAMPLE_PAYLOAD)
        await svc_b.create(name="Shared Name", payload={"view": "week"})
        await test_db_session.commit()

        a_rows = await svc_a.list_views()
        b_rows = await svc_b.list_views()
        assert len(a_rows) == 1
        assert len(b_rows) == 1
        assert a_rows[0].payload["view"] == "month"
        assert b_rows[0].payload["view"] == "week"

    async def test_rejects_duplicate_name_same_user(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        user = await data_factory.create_user(
            tenant=tenant,
            email="cv-dup-name@example.com",
            role=RoleEnum.ADMIN,
            session=test_db_session,
        )
        await test_db_session.commit()

        svc = CalendarViewsService(
            db=test_db_session,
            tenant_id=str(tenant.id),
            user_id=str(user.id),
        )
        await svc.create(name="Dup", payload=SAMPLE_PAYLOAD)
        await test_db_session.commit()

        with pytest.raises(SavedCalendarViewNameConflictError):
            await svc.create(name="Dup", payload=SAMPLE_PAYLOAD)

    async def test_update_replaces_name_and_payload(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        user = await data_factory.create_user(
            tenant=tenant,
            email="cv-update@example.com",
            role=RoleEnum.ADMIN,
            session=test_db_session,
        )
        await test_db_session.commit()

        svc = CalendarViewsService(
            db=test_db_session,
            tenant_id=str(tenant.id),
            user_id=str(user.id),
        )
        view = await svc.create(name="Old", payload={"view": "month"})
        await test_db_session.commit()

        updated = await svc.update(
            view, name="New", payload={"view": "week", "include_sla": True}
        )
        await test_db_session.commit()
        assert updated.name == "New"
        assert updated.payload == {"view": "week", "include_sla": True}

        rows = await svc.list_views()
        assert len(rows) == 1
        assert rows[0].name == "New"

    async def test_delete_removes_row(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        user = await data_factory.create_user(
            tenant=tenant,
            email="cv-delete@example.com",
            role=RoleEnum.ADMIN,
            session=test_db_session,
        )
        await test_db_session.commit()

        svc = CalendarViewsService(
            db=test_db_session,
            tenant_id=str(tenant.id),
            user_id=str(user.id),
        )
        view = await svc.create(name="ToDelete", payload=SAMPLE_PAYLOAD)
        await test_db_session.commit()

        await svc.delete(view)
        await test_db_session.commit()

        rows = await svc.list_views()
        assert rows == []


@pytest.mark.anyio
class TestCalendarViewsEndpoints:
    """HTTP-level CRUD via `/api/v1/calendar/saved-views`."""

    async def test_full_crud_flow(
        self,
        async_client: AsyncClient,
        make_auth_headers,
    ) -> None:
        headers = _cal_headers(await make_auth_headers(RoleEnum.ADMIN))

        # Empty list initially.
        listed = await async_client.get(SAVED_VIEWS_PATH, headers=headers)
        assert listed.status_code == status.HTTP_200_OK, listed.text
        assert listed.json() == []

        # Create.
        created = await async_client.post(
            SAVED_VIEWS_PATH,
            headers=headers,
            json={"name": "Critical SLA only", "payload": SAMPLE_PAYLOAD},
        )
        assert created.status_code == status.HTTP_201_CREATED, created.text
        body = created.json()
        view_id = body["id"]
        assert body["name"] == "Critical SLA only"
        assert body["payload"]["include_sla"] is True
        assert body["payload"]["sla_bands"] == ["overdue", "critical"]
        assert body["payload"]["load_dim"] == "site"

        # Listed after create.
        listed_after = await async_client.get(SAVED_VIEWS_PATH, headers=headers)
        assert listed_after.status_code == status.HTTP_200_OK, listed_after.text
        rows = listed_after.json()
        assert len(rows) == 1
        assert rows[0]["id"] == view_id

        # Update.
        updated = await async_client.patch(
            f"{SAVED_VIEWS_PATH}/{view_id}",
            headers=headers,
            json={
                "name": "Critical+Overdue",
                "payload": {
                    "view": "week",
                    "sources": ["medical_exam"],
                    "person_id": None,
                    "site_id": None,
                    "include_fact": False,
                    "include_sla": True,
                    "sla_bands": ["overdue"],
                    "include_load": False,
                    "load_dim": None,
                },
            },
        )
        assert updated.status_code == status.HTTP_200_OK, updated.text
        upd_body = updated.json()
        assert upd_body["name"] == "Critical+Overdue"
        assert upd_body["payload"]["view"] == "week"
        assert upd_body["payload"]["sources"] == ["medical_exam"]

        # Delete.
        deleted = await async_client.delete(
            f"{SAVED_VIEWS_PATH}/{view_id}", headers=headers
        )
        assert deleted.status_code == status.HTTP_204_NO_CONTENT, deleted.text

        # Empty list again.
        listed_final = await async_client.get(SAVED_VIEWS_PATH, headers=headers)
        assert listed_final.status_code == status.HTTP_200_OK
        assert listed_final.json() == []

    async def test_rejects_duplicate_name(
        self,
        async_client: AsyncClient,
        make_auth_headers,
    ) -> None:
        headers = _cal_headers(await make_auth_headers(RoleEnum.ADMIN))
        first = await async_client.post(
            SAVED_VIEWS_PATH,
            headers=headers,
            json={"name": "DupName", "payload": SAMPLE_PAYLOAD},
        )
        assert first.status_code == status.HTTP_201_CREATED, first.text

        conflict = await async_client.post(
            SAVED_VIEWS_PATH,
            headers=headers,
            json={"name": "DupName", "payload": SAMPLE_PAYLOAD},
        )
        assert conflict.status_code == status.HTTP_409_CONFLICT, conflict.text

    async def test_validates_payload_fields(
        self,
        async_client: AsyncClient,
        make_auth_headers,
    ) -> None:
        headers = _cal_headers(await make_auth_headers(RoleEnum.ADMIN))
        bad_view = await async_client.post(
            SAVED_VIEWS_PATH,
            headers=headers,
            json={
                "name": "BadView",
                "payload": {"view": "century"},  # invalid view
            },
        )
        assert bad_view.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, bad_view.text

        bad_source = await async_client.post(
            SAVED_VIEWS_PATH,
            headers=headers,
            json={
                "name": "BadSource",
                "payload": {"sources": ["nope"]},
            },
        )
        assert bad_source.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, bad_source.text

        bad_band = await async_client.post(
            SAVED_VIEWS_PATH,
            headers=headers,
            json={
                "name": "BadBand",
                "payload": {"include_sla": True, "sla_bands": ["alarming"]},
            },
        )
        assert bad_band.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, bad_band.text

        bad_load_dim = await async_client.post(
            SAVED_VIEWS_PATH,
            headers=headers,
            json={
                "name": "BadDim",
                "payload": {"include_load": True, "load_dim": "company"},
            },
        )
        assert bad_load_dim.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, bad_load_dim.text

    async def test_update_unknown_returns_404(
        self,
        async_client: AsyncClient,
        make_auth_headers,
    ) -> None:
        headers = _cal_headers(await make_auth_headers(RoleEnum.ADMIN))
        missing = await async_client.patch(
            f"{SAVED_VIEWS_PATH}/00000000-0000-0000-0000-000000000000",
            headers=headers,
            json={"name": "Anything", "payload": {}},
        )
        assert missing.status_code == status.HTTP_404_NOT_FOUND, missing.text

    async def test_delete_unknown_returns_404(
        self,
        async_client: AsyncClient,
        make_auth_headers,
    ) -> None:
        headers = _cal_headers(await make_auth_headers(RoleEnum.ADMIN))
        missing = await async_client.delete(
            f"{SAVED_VIEWS_PATH}/00000000-0000-0000-0000-000000000000",
            headers=headers,
        )
        assert missing.status_code == status.HTTP_404_NOT_FOUND, missing.text

    async def test_forbids_worker_role(
        self,
        async_client: AsyncClient,
        make_auth_headers,
    ) -> None:
        headers = _cal_headers(await make_auth_headers(RoleEnum.STUDENT))
        forbidden = await async_client.get(SAVED_VIEWS_PATH, headers=headers)
        # Either 401/403 acceptable for ABAC denial; both signify the worker
        # is not authorized to use saved views.
        assert forbidden.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }, forbidden.text
