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
from app.schemas.sout import (
    CampaignStatusUpdate,
    FactorUpdate,
    WorkplaceCreate,
    WorkplaceUpdate,
)


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


def _workplace():
    now = datetime(2026, 6, 26, tzinfo=timezone.utc)
    return SimpleNamespace(
        id="w1", tenant_id="tenant-1", campaign_id="c1",
        workplace_code="РМ-001", position_name="Сварщик", person_id=None,
        position_id=None, assessed_class=None, assessment_date=None,
        next_assessment_date=None, created_at=now, updated_at=now, deleted_at=None,
    )


def _factor():
    return SimpleNamespace(
        id="f1", tenant_id="tenant-1", workplace_id="w1", hazard_id=None,
        code="4.50", name="Шум", measured_class=None, note=None,
    )


@pytest.mark.asyncio
async def test_update_workplace_sets_position_id(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "_get_workplace", AsyncMock(return_value=_workplace()))
    monkeypatch.setattr(routes, "_validate_position", AsyncMock(return_value="pos-1"))

    out = await routes.update_workplace(
        wid="w1",
        payload=WorkplaceUpdate(position_id="pos-1"),
        tenant=_tenant(),
        session=session,
        access=SimpleNamespace(),
    )
    assert out.position_id == "pos-1"
    routes._validate_position.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_workplace_invalid_position_404(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "_get_workplace", AsyncMock(return_value=_workplace()))
    monkeypatch.setattr(
        routes,
        "_validate_position",
        AsyncMock(side_effect=routes._not_found("Position")),
    )

    with pytest.raises(Exception) as exc:
        await routes.update_workplace(
            wid="w1",
            payload=WorkplaceUpdate(position_id="missing"),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
    assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_update_factor_sets_hazard_id(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "_get_factor", AsyncMock(return_value=_factor()))
    monkeypatch.setattr(routes, "_validate_hazard", AsyncMock(return_value="haz-1"))

    out = await routes.update_factor(
        fid="f1",
        payload=FactorUpdate(hazard_id="haz-1"),
        tenant=_tenant(),
        session=session,
        access=SimpleNamespace(),
    )
    assert out.hazard_id == "haz-1"
    routes._validate_hazard.assert_awaited_once()
