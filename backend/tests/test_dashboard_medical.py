"""Task 8.2 — Dashboard: verify active MedicalSuspension count appears in overdue alerts.

Tests the _get_overdue_alerts helper of OperationalDashboardService directly against
an in-memory SQLite DB, mirroring the pattern used in test_briefings_service.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import Column, String, Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.session import TenantBase
from app.models.models import (
    MedicalSuspension,
    MedicalSuspensionReason,
    MedicalSuspensionStatus,
)
from app.modules.operational_dashboard.service import OperationalDashboardService


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


TENANT = "test-tenant"


def _make_settings() -> Settings:
    """Minimal Settings instance sufficient for OperationalDashboardService."""
    import os

    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    return Settings()


@pytest.mark.asyncio
async def test_active_suspension_appears_in_alerts(db_session) -> None:
    """An ACTIVE MedicalSuspension produces a 'medical_suspension' alert with count >= 1."""
    susp = MedicalSuspension(
        tenant_id=TENANT,
        person_id="person-1",
        reason=MedicalSuspensionReason.UNFIT,
        started_at=datetime.now(tz=timezone.utc),
        status=MedicalSuspensionStatus.ACTIVE,
    )
    db_session.add(susp)
    await db_session.flush()

    svc = OperationalDashboardService(settings=_make_settings())
    alerts = await svc._get_overdue_alerts(TENANT, db_session)

    medical_susp_alerts = [a for a in alerts if a.affected_entity_type == "medical_suspension"]
    assert medical_susp_alerts, (
        f"expected a medical_suspension alert; got entity types: "
        f"{[a.affected_entity_type for a in alerts]}"
    )
    assert medical_susp_alerts[0].count >= 1


@pytest.mark.asyncio
async def test_lifted_suspension_not_counted(db_session) -> None:
    """A LIFTED MedicalSuspension does NOT produce a medical_suspension alert."""
    susp = MedicalSuspension(
        tenant_id=TENANT,
        person_id="person-2",
        reason=MedicalSuspensionReason.UNFIT,
        started_at=datetime.now(tz=timezone.utc),
        lifted_at=datetime.now(tz=timezone.utc),
        status=MedicalSuspensionStatus.LIFTED,
    )
    db_session.add(susp)
    await db_session.flush()

    svc = OperationalDashboardService(settings=_make_settings())
    alerts = await svc._get_overdue_alerts(TENANT, db_session)

    medical_susp_alerts = [a for a in alerts if a.affected_entity_type == "medical_suspension"]
    assert (
        not medical_susp_alerts
    ), "LIFTED suspension should not produce a medical_suspension alert"


@pytest.mark.asyncio
async def test_active_suspension_tenant_scoped(db_session) -> None:
    """Suspensions from a different tenant are not counted for TENANT."""
    susp = MedicalSuspension(
        tenant_id="other-tenant",
        person_id="person-99",
        reason=MedicalSuspensionReason.UNFIT,
        started_at=datetime.now(tz=timezone.utc),
        status=MedicalSuspensionStatus.ACTIVE,
    )
    db_session.add(susp)
    await db_session.flush()

    svc = OperationalDashboardService(settings=_make_settings())
    alerts = await svc._get_overdue_alerts(TENANT, db_session)

    medical_susp_alerts = [a for a in alerts if a.affected_entity_type == "medical_suspension"]
    assert not medical_susp_alerts, "cross-tenant suspension must not appear in alert"


@pytest.mark.asyncio
async def test_full_dashboard_includes_suspension_count(db_session) -> None:
    """The full get_dashboard response includes medical_suspension in its alerts when ACTIVE ones exist."""
    susp = MedicalSuspension(
        tenant_id=TENANT,
        person_id="person-3",
        reason=MedicalSuspensionReason.CONTRAINDICATION,
        started_at=datetime.now(tz=timezone.utc),
        status=MedicalSuspensionStatus.ACTIVE,
    )
    db_session.add(susp)
    await db_session.flush()

    svc = OperationalDashboardService(settings=_make_settings())
    resp = await svc.get_dashboard(TENANT, db=db_session)

    entity_types = {a.affected_entity_type for a in resp.alerts}
    assert (
        "medical_suspension" in entity_types
    ), f"medical_suspension not in full dashboard response; got {entity_types}"
