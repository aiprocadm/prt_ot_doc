"""API-contract tests for СОУТ routes (P10-04), mocking session.

Follows the repo convention (see test_committees_api.py): patch the route
module's getters with AsyncMock — no live DB.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import sout as routes
from app.models.sout import SoutCampaignStatus
from app.schemas.sout import CampaignStatusUpdate, WorkplaceCreate


def _tenant():
    return SimpleNamespace(id="tenant-1", is_active=True, slug="t1")


def _campaign(status=SoutCampaignStatus.PLANNED):
    now = datetime(2026, 6, 26, tzinfo=timezone.utc)
    return SimpleNamespace(
        id="c1", tenant_id="tenant-1", name="СОУТ 2026",
        expert_org_name=None, report_number=None, report_date=None,
        status=status, planned_date=None, completed_date=None,
        created_at=now, updated_at=now, deleted_at=None,
    )


@pytest.mark.asyncio
async def test_transition_campaign_rejects_illegal(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(
        routes, "_get_campaign", AsyncMock(return_value=_campaign(SoutCampaignStatus.PLANNED))
    )
    with pytest.raises(Exception) as exc:
        await routes.update_campaign_status(
            cid="c1",
            payload=CampaignStatusUpdate(status=SoutCampaignStatus.COMPLETED),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
    assert getattr(exc.value, "status_code", None) == 409


@pytest.mark.asyncio
async def test_add_workplace_rejected_on_closed_campaign(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(
        routes, "_get_campaign", AsyncMock(return_value=_campaign(SoutCampaignStatus.COMPLETED))
    )
    with pytest.raises(Exception) as exc:
        await routes.add_workplace(
            cid="c1",
            payload=WorkplaceCreate(workplace_code="РМ-001", position_name="Сварщик"),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
    assert getattr(exc.value, "status_code", None) == 409


@pytest.mark.asyncio
async def test_add_workplace_allowed_on_open_campaign(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(
        routes, "_get_campaign", AsyncMock(return_value=_campaign(SoutCampaignStatus.IN_PROGRESS))
    )

    created = {}

    async def _flush():
        return None

    async def _refresh(obj):
        # mimic DB defaults populated on refresh
        obj.id = obj.id or "w-new"
        obj.created_at = datetime(2026, 6, 26, tzinfo=timezone.utc)
        obj.updated_at = datetime(2026, 6, 26, tzinfo=timezone.utc)

    def _add(obj):
        created["obj"] = obj
        obj.id = "w-new"

    session.flush = _flush
    session.refresh = _refresh
    session.add = _add

    out = await routes.add_workplace(
        cid="c1",
        payload=WorkplaceCreate(workplace_code="РМ-001", position_name="Сварщик"),
        tenant=_tenant(),
        session=session,
        access=SimpleNamespace(),
    )
    assert out.workplace_code == "РМ-001"
    assert out.campaign_id == "c1"
    assert out.is_reassessment_due is False
