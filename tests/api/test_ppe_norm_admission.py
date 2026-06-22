"""Norm-aware PPE admission gate: 766н card lines drive the ``ppe_issue`` check.

Mirrors ``test_medical_contingent_admission.py`` (Task 7.2 norm-aware medical):
when PPE norms exist for the person's position, every required card line must
be covered by an active issue that is not overdue (ok / due_soon pass,
overdue / missing block). Without norms the legacy any-active-issue check
stays in force. The violation code is the pre-existing ``ppe_issue``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.models import Position, PPEIssue, PPEItem, PPENorm
from app.models.risk import RiskHazard
from app.services.person_admission import enforce_person_admission

NOW = datetime.now(tz=timezone.utc)


async def _world(session, data_factory, *, tag: str):
    """Tenant + company + position + hazard + person on that position."""
    tenant = await data_factory.ensure_tenant(session=session)
    company = await data_factory.create_company(
        tenant=tenant, session=session, name=f"PPE-Gate {tag}"
    )
    position = Position(tenant_id=tenant.id, company_id=company.id, name=f"PPE-Gate-{tag}")
    hazard = RiskHazard(tenant_id=tenant.id, code=f"ppegate-{tag}", title=f"Фактор {tag}")
    session.add_all([position, hazard])
    await session.flush()
    person = await data_factory.create_person(
        tenant=tenant, company=company, session=session, position_id=position.id
    )
    return tenant, position, hazard, person


def _norm(tenant, position, hazard, item, *, quantity: int = 1) -> PPENorm:
    return PPENorm(
        tenant_id=tenant.id,
        position_id=position.id,
        hazard_id=hazard.id,
        item_id=item.id,
        item_name=item.name,
        quantity=quantity,
        interval_days=365,
    )


def _issue(
    tenant,
    person,
    *,
    item_id=None,
    item_name: str,
    quantity: int = 1,
    expires_in_days: int | None = 300,
) -> PPEIssue:
    expires = NOW + timedelta(days=expires_in_days) if expires_in_days is not None else None
    return PPEIssue(
        tenant_id=tenant.id,
        person_id=person.id,
        item_id=item_id,
        item_name=item_name,
        quantity=quantity,
        issued_at=NOW - timedelta(days=1),
        expires_at=expires,
        status="issued",
    )


async def _violations_for(session, tenant, person) -> str:
    with pytest.raises(ValueError) as ei:
        await enforce_person_admission(session, tenant_scope=(str(tenant.id),), persons=[person])
    return str(ei.value)


@pytest.mark.asyncio
async def test_norm_overdue_issue_blocks_even_with_other_active_issue(sessionmaker, data_factory):
    """Overdue normed line blocks although the legacy any-active check would pass."""
    async with sessionmaker() as session:
        tenant, position, hazard, person = await _world(session, data_factory, tag="ovd")
        helmet = PPEItem(tenant_id=tenant.id, name="Каска ovd", default_wear_days=730)
        session.add(helmet)
        await session.flush()
        session.add(_norm(tenant, position, hazard, helmet))
        # normed line: active but expired → overdue
        session.add(
            _issue(tenant, person, item_id=helmet.id, item_name=helmet.name, expires_in_days=-5)
        )
        # unrelated active issue — satisfies the LEGACY any-active check
        session.add(_issue(tenant, person, item_name="Перчатки вне нормы ovd"))
        await session.commit()

        assert "ppe_issue" in await _violations_for(session, tenant, person)


@pytest.mark.asyncio
async def test_all_norm_lines_covered_passes(sessionmaker, data_factory):
    """ok + due_soon lines both pass the gate (no ppe_issue violation)."""
    async with sessionmaker() as session:
        tenant, position, hazard, person = await _world(session, data_factory, tag="ok")
        helmet = PPEItem(tenant_id=tenant.id, name="Каска ok", default_wear_days=730)
        belt = PPEItem(tenant_id=tenant.id, name="Пояс ok", default_wear_days=365)
        session.add_all([helmet, belt])
        await session.flush()
        session.add_all(
            [
                _norm(tenant, position, hazard, helmet),
                _norm(tenant, position, hazard, belt),
            ]
        )
        session.add(
            _issue(tenant, person, item_id=helmet.id, item_name=helmet.name, expires_in_days=300)
        )  # ok
        session.add(
            _issue(tenant, person, item_id=belt.id, item_name=belt.name, expires_in_days=10)
        )  # due_soon
        await session.commit()

        # training/medical are absent so admission still raises — but NOT for PPE
        assert "ppe_issue" not in await _violations_for(session, tenant, person)


@pytest.mark.asyncio
async def test_missing_issue_for_one_norm_blocks(sessionmaker, data_factory):
    """One uncovered norm line blocks even though another line is covered."""
    async with sessionmaker() as session:
        tenant, position, hazard, person = await _world(session, data_factory, tag="mis")
        helmet = PPEItem(tenant_id=tenant.id, name="Каска mis", default_wear_days=730)
        gloves = PPEItem(tenant_id=tenant.id, name="Перчатки mis", default_wear_days=30)
        session.add_all([helmet, gloves])
        await session.flush()
        session.add_all(
            [
                _norm(tenant, position, hazard, helmet),
                _norm(tenant, position, hazard, gloves),
            ]
        )
        # only the helmet line is covered; gloves line → missing
        session.add(_issue(tenant, person, item_id=helmet.id, item_name=helmet.name))
        await session.commit()

        assert "ppe_issue" in await _violations_for(session, tenant, person)


@pytest.mark.asyncio
async def test_partial_quantity_blocks(sessionmaker, data_factory):
    """Norm requires 2, only 1 active issued → missing → blocked."""
    async with sessionmaker() as session:
        tenant, position, hazard, person = await _world(session, data_factory, tag="qty")
        gloves = PPEItem(tenant_id=tenant.id, name="Перчатки qty", default_wear_days=30)
        session.add(gloves)
        await session.flush()
        session.add(_norm(tenant, position, hazard, gloves, quantity=2))
        session.add(_issue(tenant, person, item_id=gloves.id, item_name=gloves.name, quantity=1))
        await session.commit()

        assert "ppe_issue" in await _violations_for(session, tenant, person)


@pytest.mark.asyncio
async def test_no_norms_legacy_pass_preserved(sessionmaker, data_factory):
    """Position without PPE norms: any active non-expired issue still passes."""
    async with sessionmaker() as session:
        tenant, position, hazard, person = await _world(session, data_factory, tag="lgp")
        session.add(_issue(tenant, person, item_name="Любая выдача lgp"))
        await session.commit()

        assert "ppe_issue" not in await _violations_for(session, tenant, person)


@pytest.mark.asyncio
async def test_no_norms_legacy_fail_preserved(sessionmaker, data_factory):
    """Position without PPE norms and no issues: legacy check still blocks."""
    async with sessionmaker() as session:
        tenant, position, hazard, person = await _world(session, data_factory, tag="lgf")
        await session.commit()

        assert "ppe_issue" in await _violations_for(session, tenant, person)


@pytest.mark.asyncio
async def test_legacy_item_name_only_norm_matches_catalog_issue(sessionmaker, data_factory):
    """Pre-sz01 norm (item_id=None) is satisfied by a same-name catalog issue."""
    async with sessionmaker() as session:
        tenant, position, hazard, person = await _world(session, data_factory, tag="nam")
        item = PPEItem(tenant_id=tenant.id, name="Респиратор nam", default_wear_days=180)
        session.add(item)
        await session.flush()
        session.add(
            PPENorm(  # legacy: no catalog link
                tenant_id=tenant.id,
                position_id=position.id,
                hazard_id=hazard.id,
                item_id=None,
                item_name=item.name,
                quantity=1,
                interval_days=180,
            )
        )
        session.add(_issue(tenant, person, item_id=item.id, item_name=item.name))
        await session.commit()

        assert "ppe_issue" not in await _violations_for(session, tenant, person)
