from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import tasks
from app.db import Base, SharedBase
from app.models.models import Template, TemplateVersion, Tenant


def _prepare_sqlite_metadata() -> None:
    SharedBase.metadata.schema = None
    for table in SharedBase.metadata.tables.values():
        table.schema = None
    if "tenant" not in Base.metadata.tables:
        Tenant.__table__.tometadata(Base.metadata, schema=None)


def test_register_template_task(monkeypatch) -> None:
    async def setup():
        _prepare_sqlite_metadata()
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
        async with engine.begin() as conn:
            await conn.run_sync(SharedBase.metadata.create_all)
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with session_factory() as session:
            tenant = Tenant(slug="demo", name="Demo", contact_email="demo@example.com")
            session.add(tenant)
            await session.commit()
            await session.refresh(tenant)
        return engine, session_factory, tenant

    engine, TestSession, tenant = asyncio.run(setup())

    @asynccontextmanager
    async def override_scope(*, tenant: str | None = None):
        async with TestSession() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    monkeypatch.setattr(tasks, "session_scope", override_scope)

    version_id = tasks.register_template_task(
        tenant.slug,
        name="Procedure",
        storage_key="demo/templates/procedure.docx",
        checksum_hex="00" * 32,
        description="Demo template",
        metadata={"category": "demo"},
    )

    async def fetch():
        async with TestSession() as session:
            template = (
                await session.execute(select(Template).where(Template.name == "Procedure"))
            ).scalar_one()
            version = (
                await session.execute(
                    select(TemplateVersion).where(TemplateVersion.id == version_id)
                )
            ).scalar_one()
            return template, version

    template, version = asyncio.run(fetch())
    assert template.tenant_id == tenant.id
    assert version.template_id == template.id

    asyncio.run(engine.dispose())
