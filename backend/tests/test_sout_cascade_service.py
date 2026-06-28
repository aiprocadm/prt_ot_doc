"""Тесты сервиса каскада СОУТ (in-memory SQLite)."""
import pytest
from sqlalchemy import Column, String, Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models.models  # noqa: F401 — регистрирует medical/ppe/position
import app.models.risk  # noqa: F401 — регистрирует risk_hazards
import app.models.sout  # noqa: F401 — регистрирует sout-таблицы
from app.db.session import TenantBase
from app.models.models import Company, MedicalExamKind, MedicalFactor, MedicalNorm, Position
from app.models.risk import RiskHazard
from app.models.sout import SoutCampaign, SoutClass, SoutFactor, SoutWorkplace
from app.services.sout_cascade import apply_cascade, preview_cascade


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


class _Tenant:
    def __init__(self, tid="tenant-1"):
        self.id = tid


@pytest.fixture()
async def seeded(db_session):
    """Кампания (PLANNED=open) с РМ класса 3.1, должностью, hazard→29н фактор periodic/12мес."""
    t = _Tenant()
    company = Company(tenant_id=t.id, name="ООО Ромашка")
    db_session.add(company)
    await db_session.flush()
    pos = Position(tenant_id=t.id, company_id=company.id, name="Слесарь")
    db_session.add(pos)
    await db_session.flush()
    db_session.add(MedicalFactor(
        tenant_id=t.id, code="4.1", name="Шум", category="factor",
        exam_kinds=["periodic"], periodicity_months=12,
    ))
    haz = RiskHazard(tenant_id=t.id, code="H-4.1", title="Шум", medical_factor_code="4.1")
    db_session.add(haz)
    await db_session.flush()
    c = SoutCampaign(tenant_id=t.id, name="СОУТ 2026")  # default status PLANNED ∈ _OPEN_STATUSES
    db_session.add(c)
    await db_session.flush()
    wp = SoutWorkplace(
        tenant_id=t.id, campaign_id=c.id, workplace_code="РМ-01",
        position_name="Слесарь", position_id=pos.id, assessed_class=SoutClass.HARMFUL_3_1,
    )
    db_session.add(wp)
    await db_session.flush()
    db_session.add(SoutFactor(
        tenant_id=t.id, workplace_id=wp.id, name="Шум", code="4.1",
        hazard_id=haz.id, measured_class=SoutClass.HARMFUL_3_1,
    ))
    await db_session.flush()
    return t, c, wp, pos


@pytest.mark.asyncio
async def test_preview_proposes_create(db_session, seeded):
    t, c, wp, pos = seeded
    preview = await preview_cascade(db_session, _Tenant(), wp.id)
    assert preview is not None
    assert preview.assessed_class == "harmful_3_1"
    assert [a.op for a in preview.medical] == ["create"]
    assert preview.can_apply is True


@pytest.mark.asyncio
async def test_preview_none_when_workplace_missing(db_session, seeded):
    preview = await preview_cascade(db_session, _Tenant(), "no-such-id")
    assert preview is None


@pytest.mark.asyncio
async def test_apply_creates_medical_norm_with_class(db_session, seeded):
    t, c, wp, pos = seeded
    result = await apply_cascade(db_session, _Tenant(), wp.id)
    assert result is not None
    assert result.created == 1
    norms = list((await db_session.execute(
        select(MedicalNorm).where(MedicalNorm.position_id == pos.id)
    )).scalars().all())
    assert len(norms) == 1
    assert norms[0].exam_kind == MedicalExamKind.PERIODIC
    assert norms[0].working_conditions_class == "harmful_3_1"
    assert norms[0].hazard_id is None
    assert norms[0].interval_days == 365


@pytest.mark.asyncio
async def test_apply_is_idempotent(db_session, seeded):
    t, c, wp, pos = seeded
    await apply_cascade(db_session, _Tenant(), wp.id)
    second = await apply_cascade(db_session, _Tenant(), wp.id)
    assert second.created == 0 and second.reclassified == 0


@pytest.mark.asyncio
async def test_apply_reclass_only_when_empty(db_session, seeded):
    t, c, wp, pos = seeded
    db_session.add(MedicalNorm(
        tenant_id=t.id, position_id=pos.id, exam_kind=MedicalExamKind.PERIODIC,
        hazard_id=None, interval_days=365, working_conditions_class=None,
    ))
    await db_session.flush()
    result = await apply_cascade(db_session, _Tenant(), wp.id)
    assert result.reclassified == 1 and result.created == 0
    norm = (await db_session.execute(
        select(MedicalNorm).where(MedicalNorm.position_id == pos.id)
    )).scalar_one()
    assert norm.working_conditions_class == "harmful_3_1"


@pytest.mark.asyncio
async def test_apply_conflict_not_overwritten(db_session, seeded):
    t, c, wp, pos = seeded
    db_session.add(MedicalNorm(
        tenant_id=t.id, position_id=pos.id, exam_kind=MedicalExamKind.PERIODIC,
        hazard_id=None, interval_days=365, working_conditions_class="acceptable",
    ))
    await db_session.flush()
    result = await apply_cascade(db_session, _Tenant(), wp.id)
    assert result.conflicts == 1 and result.created == 0 and result.reclassified == 0
    norm = (await db_session.execute(
        select(MedicalNorm).where(MedicalNorm.position_id == pos.id)
    )).scalar_one()
    assert norm.working_conditions_class == "acceptable"  # не перезаписан
