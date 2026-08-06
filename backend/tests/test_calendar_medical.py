"""Task 8.1 — Calendar: verify medical_referral events appear in aggregator output.

Tests the _build_medical_referrals builder by calling the CalendarAggregatorService
directly against an in-memory SQLite DB, mirroring the pattern in
backend/tests/test_briefings_service.py.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import Column, String, Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import TenantBase
from app.models.models import (
    MedicalExamKind,
    MedicalReferral,
    MedicalReferralStatus,
)
from app.services.calendar_aggregator import CalendarAggregatorService


@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    # Ensure the shared tenant stub table exists so FK-less tenant_id cols work
    if "tenant" not in TenantBase.metadata.tables:
        Table("tenant", TenantBase.metadata, Column("id", String(36), primary_key=True))
    async with engine.begin() as conn:
        await conn.run_sync(TenantBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


TENANT = "test-tenant"


@pytest.mark.asyncio
async def test_build_medical_referrals_future_due_at(db_session) -> None:
    """A referral with due_at in the future appears as source_type='medical_referral', status='active'."""
    future_due = date.today() + timedelta(days=10)
    ref = MedicalReferral(
        tenant_id=TENANT,
        person_id="person-1",
        exam_kind=MedicalExamKind.PERIODIC,
        due_at=future_due,
        status=MedicalReferralStatus.ISSUED,
    )
    db_session.add(ref)
    await db_session.flush()

    svc = CalendarAggregatorService(tenant_id=TENANT, db=db_session)
    resp = await svc.list_events(source_types=["medical_referral"])

    ids = [item.id for item in resp.items]
    assert any(
        i.startswith("medical_referral:") for i in ids
    ), f"expected medical_referral:... item, got {ids}"
    item = next(i for i in resp.items if i.id.startswith("medical_referral:"))
    assert item.source_type == "medical_referral"
    assert item.status == "active"
    assert item.is_overdue is False
    assert item.person_id == "person-1"
    assert "periodic" in item.title


@pytest.mark.asyncio
async def test_build_medical_referrals_overdue(db_session) -> None:
    """A referral with due_at in the past is marked expired/overdue."""
    past_due = date.today() - timedelta(days=5)
    ref = MedicalReferral(
        tenant_id=TENANT,
        person_id="person-2",
        exam_kind=MedicalExamKind.PRELIMINARY,
        due_at=past_due,
        status=MedicalReferralStatus.ISSUED,
    )
    db_session.add(ref)
    await db_session.flush()

    svc = CalendarAggregatorService(tenant_id=TENANT, db=db_session)
    resp = await svc.list_events(source_types=["medical_referral"])

    item = next(
        (
            i
            for i in resp.items
            if i.id.startswith("medical_referral:") and i.person_id == "person-2"
        ),
        None,
    )
    assert item is not None, "overdue referral not found in calendar items"
    assert item.status == "expired"
    assert item.is_overdue is True


@pytest.mark.asyncio
async def test_build_medical_referrals_null_due_at_excluded(db_session) -> None:
    """Referrals with due_at=NULL are excluded (no anchor date)."""
    ref = MedicalReferral(
        tenant_id=TENANT,
        person_id="person-3",
        exam_kind=MedicalExamKind.PERIODIC,
        due_at=None,
        status=MedicalReferralStatus.ISSUED,
    )
    db_session.add(ref)
    await db_session.flush()

    svc = CalendarAggregatorService(tenant_id=TENANT, db=db_session)
    resp = await svc.list_events(source_types=["medical_referral"])

    person3_items = [i for i in resp.items if i.person_id == "person-3"]
    assert person3_items == [], "referral with null due_at should not appear in calendar"


@pytest.mark.asyncio
async def test_build_medical_referrals_tenant_scoped(db_session) -> None:
    """Referrals for another tenant are not returned."""
    future_due = date.today() + timedelta(days=5)
    ref_other = MedicalReferral(
        tenant_id="other-tenant",
        person_id="person-99",
        exam_kind=MedicalExamKind.PERIODIC,
        due_at=future_due,
        status=MedicalReferralStatus.ISSUED,
    )
    db_session.add(ref_other)
    await db_session.flush()

    svc = CalendarAggregatorService(tenant_id=TENANT, db=db_session)
    resp = await svc.list_events(source_types=["medical_referral"])

    other_tenant_items = [i for i in resp.items if i.person_id == "person-99"]
    assert other_tenant_items == [], "cross-tenant leakage in calendar_referral builder"


@pytest.mark.asyncio
async def test_medical_referral_appears_in_all_sources_response(db_session) -> None:
    """medical_referral is included in the ALL_SOURCES aggregation and by_source reflects it."""
    future_due = date.today() + timedelta(days=3)
    ref = MedicalReferral(
        tenant_id=TENANT,
        person_id="person-4",
        exam_kind=MedicalExamKind.PERIODIC,
        due_at=future_due,
        status=MedicalReferralStatus.ISSUED,
    )
    db_session.add(ref)
    await db_session.flush()

    svc = CalendarAggregatorService(tenant_id=TENANT, db=db_session)
    # Call with default ALL_SOURCES
    resp = await svc.list_events()

    source_types_in_by_source = {s.source_type for s in resp.by_source}
    assert (
        "medical_referral" in source_types_in_by_source
    ), "medical_referral not in by_source even though ALL_SOURCES includes it"
