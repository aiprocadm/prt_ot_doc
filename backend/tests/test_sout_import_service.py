"""Тесты сервиса импорта СОУТ + схем (часть без БД)."""


def test_import_preview_schema_roundtrip():
    from app.schemas.sout import ImportFactorRow, ImportPreview, ImportWorkplaceRow

    row = ImportWorkplaceRow(
        row_index=0, workplace_code="РМ-01", position_name="Слесарь",
        parsed_class="acceptable", current_class=None, change="new",
        factors=[ImportFactorRow(code=None, name="Шум", parsed_class="harmful_3_1", class_unparsed=None)],
        errors=[], warnings=["класс 1-2, но указан вредный фактор (3.1+)"],
    )
    preview = ImportPreview(
        campaign_id="c1", rows=[row], new_count=1, changed_count=0,
        unchanged_count=0, removed_count=0, error_count=0, can_apply=True,
    )
    assert preview.rows[0].change == "new"
    assert preview.can_apply is True


import pytest
from sqlalchemy import Column, String, Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import TenantBase
import app.models.sout  # noqa: F401  — регистрирует sout-таблицы в metadata
from app.models.sout import SoutCampaign, SoutClass, SoutClassHistory, SoutFactor, SoutWorkplace
from app.services.sout_import import ImportValidationError, apply_import, preview_import


# Локальная in-memory SQLite сессия (паттерн test_dq_medical.py — общего conftest нет).
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


def _csv(rows: str) -> bytes:
    header = "workplace_code,position_name,assessed_class,factor_name,factor_class\n"
    return (header + rows).encode("utf-8")


@pytest.fixture()
async def campaign(db_session):
    t = _Tenant()
    c = SoutCampaign(tenant_id=t.id, name="СОУТ 2026")
    db_session.add(c)
    await db_session.flush()
    db_session.add(SoutWorkplace(
        tenant_id=t.id, campaign_id=c.id, workplace_code="РМ-01",
        position_name="Слесарь", assessed_class=SoutClass.ACCEPTABLE,
    ))
    await db_session.flush()
    return t, c


@pytest.mark.asyncio
async def test_preview_classifies_new_changed_unchanged(db_session, campaign):
    t, c = campaign
    content = _csv(
        "РМ-01,Слесарь,3.1,,\n"     # changed (было acceptable)
        "РМ-02,Сварщик,2,,\n"        # new
    )
    preview = await preview_import(db_session, tenant=t, campaign_id=c.id, content=content, filename="r.csv")
    by_code = {r.workplace_code: r for r in preview.rows}
    assert by_code["РМ-01"].change == "changed"
    assert by_code["РМ-02"].change == "new"
    assert preview.new_count == 1 and preview.changed_count == 1
    assert preview.can_apply is True


@pytest.mark.asyncio
async def test_preview_missing_campaign_returns_none(db_session):
    t = _Tenant()
    out = await preview_import(db_session, tenant=t, campaign_id="nope", content=_csv("РМ-9,X,2,,\n"), filename="r.csv")
    assert out is None


@pytest.mark.asyncio
async def test_apply_creates_updates_and_writes_history(db_session, campaign):
    t, c = campaign
    content = _csv(
        "РМ-01,Слесарь,3.1,,\n"          # changed → history old=acceptable new=3.1
        "РМ-02,Сварщик,2,Шум,3.1\n"      # new + factor
    )
    result = await apply_import(db_session, tenant=t, campaign_id=c.id, content=content, filename="r.csv")
    assert result.created == 1 and result.updated == 1
    await db_session.flush()
    wps = (await db_session.execute(
        select(SoutWorkplace).where(SoutWorkplace.campaign_id == c.id)
    )).scalars().all()
    assert {w.workplace_code for w in wps} == {"РМ-01", "РМ-02"}
    rm01 = next(w for w in wps if w.workplace_code == "РМ-01")
    assert rm01.assessed_class == SoutClass.HARMFUL_3_1
    factors = (await db_session.execute(select(SoutFactor))).scalars().all()
    assert any(f.name == "Шум" and f.measured_class == SoutClass.HARMFUL_3_1 for f in factors)
    hist = (await db_session.execute(select(SoutClassHistory))).scalars().all()
    assert any(h.new_class == SoutClass.HARMFUL_3_1 for h in hist)


@pytest.mark.asyncio
async def test_apply_all_or_nothing_on_blocking_error(db_session, campaign):
    t, c = campaign
    content = _csv("РМ-03,,2,,\n")  # пустая должность → блокирующая ошибка
    with pytest.raises(ImportValidationError):
        await apply_import(db_session, tenant=t, campaign_id=c.id, content=content, filename="r.csv")
    wps = (await db_session.execute(
        select(SoutWorkplace).where(SoutWorkplace.workplace_code == "РМ-03")
    )).scalars().all()
    assert wps == []


@pytest.mark.asyncio
async def test_apply_idempotent_second_run_is_noop(db_session, campaign):
    t, c = campaign
    content = _csv("РМ-01,Слесарь,2,,\n")  # совпадает с существующим → unchanged
    result = await apply_import(db_session, tenant=t, campaign_id=c.id, content=content, filename="r.csv")
    assert result.created == 0 and result.updated == 0 and result.skipped == 1
