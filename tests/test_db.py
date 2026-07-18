from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import db
from app.db import SharedBase
from app.db import session as db_session
from app.models.models import Company, Tenant
from app.repository import create_company
from app.schemas.company import CompanyCreate


def _prepare_sqlite_metadata() -> None:
    SharedBase.metadata.schema = None
    for table in SharedBase.metadata.tables.values():
        table.schema = None
    if "tenant" not in db.Base.metadata.tables:
        Tenant.__table__.tometadata(db.Base.metadata, schema=None)


async def _prepare_database(engine) -> tuple[async_sessionmaker, Tenant]:
    _prepare_sqlite_metadata()
    async with engine.begin() as conn:
        await conn.run_sync(SharedBase.metadata.create_all)
        await conn.run_sync(db.Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        tenant = Tenant(
            slug="test",
            name="Test",
            contact_email="test@example.com",
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        return session_factory, tenant


@pytest.mark.asyncio
async def test_session_scope_commit(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    SessionFactory, tenant = await _prepare_database(engine)

    monkeypatch.setattr(db_session, "SessionLocal", SessionFactory)
    monkeypatch.setattr(
        db_session, "AsyncSessionLocal", lambda *args, **kwargs: SessionFactory(), raising=False
    )
    monkeypatch.setattr(db, "SessionLocal", SessionFactory, raising=False)
    monkeypatch.setattr(
        db, "AsyncSessionLocal", lambda *args, **kwargs: SessionFactory(), raising=False
    )

    async with db.session_scope(tenant=tenant.slug) as session:
        await create_company(session, tenant.id, CompanyCreate(name="Committed"))

    async with SessionFactory() as session:
        result = await session.execute(select(Company).where(Company.name == "Committed"))
        assert result.scalar_one() is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_session_scope_rollback(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    SessionFactory, tenant = await _prepare_database(engine)

    monkeypatch.setattr(db_session, "SessionLocal", SessionFactory)
    monkeypatch.setattr(
        db_session, "AsyncSessionLocal", lambda *args, **kwargs: SessionFactory(), raising=False
    )
    monkeypatch.setattr(db, "SessionLocal", SessionFactory, raising=False)
    monkeypatch.setattr(
        db, "AsyncSessionLocal", lambda *args, **kwargs: SessionFactory(), raising=False
    )

    with pytest.raises(RuntimeError):
        async with db.session_scope(tenant=tenant.slug) as session:
            await create_company(session, tenant.id, CompanyCreate(name="To Rollback"))
            raise RuntimeError("boom")

    async with SessionFactory() as session:
        result = await session.execute(select(Company))
        assert result.scalars().all() == []

    await engine.dispose()
