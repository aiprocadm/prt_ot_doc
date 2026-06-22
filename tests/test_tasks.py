from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.tasks as tasks
import app.tasks._core as tasks_core
from app.db import Base, SharedBase
from app.models.job_engine import OutboxEvent, OutboxEventStatus
from app.models.models import Template, TemplateVersion, Tenant, WebhookDelivery, WebhookEndpoint


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

    monkeypatch.setattr(tasks_core, "session_scope", override_scope)

    version_id = tasks.register_template_task(
        tenant.slug,
        name="Procedure",
        storage_key="demo/templates/procedure.docx",
        checksum_hex="00" * 32,
        description="Demo template",
        metadata={"category": "demo"},
        version_metadata={
            "document_type": "instruction",
            "required_fields_schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            "applicability_rules": {},
            "output_types": ["docx"],
            "profile": {},
        },
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


def test_dispatch_outbox_events_resolves_webhook_endpoints_by_tenant_id(monkeypatch) -> None:
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
            await session.flush()
            endpoint = WebhookEndpoint(
                tenant_id=tenant.id,
                name="Primary webhook",
                url="https://example.test/webhooks/outbox",
                is_enabled=True,
                subscribed_events=[],
                timeout_ms=1000,
            )
            event = OutboxEvent(
                tenant_id=tenant.id,
                event_type="CustomEvent",
                aggregate_type="document",
                aggregate_id="doc-1",
                event_id="evt-1",
                payload={"document_id": "doc-1"},
                status=OutboxEventStatus.PENDING.value,
                attempts=0,
            )
            session.add_all([endpoint, event])
            await session.commit()
            await session.refresh(tenant)
        return engine, session_factory, tenant

    engine, TestSession, tenant = asyncio.run(setup())

    @asynccontextmanager
    async def override_scope(*, tenant: str | None = None):
        async with TestSession() as session:
            session.info["tenant_id"] = tenant_obj.id
            session.info["tenant_slug"] = tenant_obj.slug
            session.info["tenant"] = tenant_obj.slug
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    tenant_obj = tenant
    monkeypatch.setattr(tasks_core, "session_scope", override_scope)

    calls: list[dict[str, object]] = []

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url, *, content, headers, timeout):
            calls.append({"url": url, "content": content, "headers": headers, "timeout": timeout})
            return SimpleNamespace(status_code=204, text="")

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(AsyncClient=_FakeAsyncClient))

    processed = asyncio.run(tasks._dispatch_outbox_events(max_attempts=3, tenant_slug=tenant.slug))

    async def fetch():
        async with TestSession() as session:
            event = (
                await session.execute(select(OutboxEvent).where(OutboxEvent.event_id == "evt-1"))
            ).scalar_one()
            deliveries = (await session.execute(select(WebhookDelivery))).scalars().all()
            return event, deliveries

    event, deliveries = asyncio.run(fetch())
    assert processed == 1
    assert len(calls) == 1
    assert calls[0]["headers"]["X-Tenant"] == tenant.id
    assert event.status == OutboxEventStatus.SENT.value
    assert len(deliveries) == 1
    assert deliveries[0].endpoint_id
    assert deliveries[0].tenant_id == tenant.id

    asyncio.run(engine.dispose())
