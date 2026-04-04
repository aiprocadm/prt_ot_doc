"""Два tenant: изоляция при dispatch outbox, доступ к webhook delivery, GET документа по id."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.security import issue_access_token
from app.db.session import AsyncSessionLocal
from app.middleware.tenant import TenantMiddleware
from app.models.models import Outbox, OutboxStatus, RoleEnum, Tenant, WebhookDelivery, WebhookEndpoint
from app.services.outbox import OutboxProcessor


async def _ensure_global_tenant(*, slug: str = "test", tenant_id: str | None = None) -> None:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False
    ) as session:
        existing = (
            await session.execute(select(Tenant).where(Tenant.slug == slug))
        ).scalar_one_or_none()
        if existing is not None:
            return
        payload: dict[str, object] = {"slug": slug, "name": slug.title(), "contact_email": f"{slug}@example.com"}
        if tenant_id is not None:
            payload["id"] = tenant_id
        session.add(Tenant(**payload))
        await session.commit()


@pytest.fixture(autouse=True)
def _bypass_tenant_middleware(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _dispatch_passthrough(self, request, call_next):  # type: ignore[no-untyped-def]
        return await call_next(request)

    monkeypatch.setattr(TenantMiddleware, "dispatch", _dispatch_passthrough)


class _DummyDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def dispatch(
        self,
        *,
        event_type: str,
        tenant_id: str,
        payload: dict,
        destination: str,
        headers: dict | None = None,
        idempotency_key: str | None = None,
        session=None,
    ) -> None:
        self.calls.append(
            {
                "event_type": event_type,
                "tenant_id": tenant_id,
                "payload": payload,
                "destination": destination,
                "headers": headers or {},
                "idempotency_key": idempotency_key,
            }
        )


@pytest.mark.anyio
async def test_outbox_processor_dispatch_keeps_tenant_id_aligned_with_each_row(
    sessionmaker,
    data_factory,
) -> None:
    """В одном batch две записи разных аренд — в dispatcher уходит тот же tenant_id, что у строки outbox."""
    now = datetime.now(tz=timezone.utc) - timedelta(seconds=1)
    async with sessionmaker() as session:
        ta = await data_factory.ensure_tenant(slug="outbox-tenant-a", session=session)
        tb = await data_factory.ensure_tenant(slug="outbox-tenant-b", session=session)
        dest = "https://example.test/hooks/two-tenant"
        session.add_all(
            [
                Outbox(
                    tenant_id=ta.id,
                    event_type="DocumentCreated",
                    destination=dest,
                    payload={"marker": "a"},
                    status=OutboxStatus.PENDING,
                    next_attempt_at=now,
                    idempotency_key="idem-outbox-a",
                ),
                Outbox(
                    tenant_id=tb.id,
                    event_type="DocumentCreated",
                    destination=dest,
                    payload={"marker": "b"},
                    status=OutboxStatus.PENDING,
                    next_attempt_at=now,
                    idempotency_key="idem-outbox-b",
                ),
            ]
        )
        await session.commit()

    dispatcher = _DummyDispatcher()
    async with sessionmaker() as session:
        processor = OutboxProcessor(session, dispatcher=dispatcher)
        processed = await processor.process_once()

    assert processed == 2
    assert len(dispatcher.calls) == 2
    by_tenant = {str(c["tenant_id"]): c for c in dispatcher.calls}
    assert set(by_tenant) == {ta.id, tb.id}
    assert by_tenant[ta.id]["payload"]["marker"] == "a"
    assert by_tenant[tb.id]["payload"]["marker"] == "b"


@pytest.mark.anyio
async def test_get_webhook_delivery_diagnostics_404_when_delivery_belongs_to_different_tenant(
    async_client,
    make_auth_headers,
    sessionmaker,
    data_factory,
) -> None:
    async with sessionmaker() as session:
        tenant_owner = await data_factory.ensure_tenant(slug="wh-owner", session=session)
        tenant_other = await data_factory.ensure_tenant(slug="wh-other", session=session)
        endpoint = WebhookEndpoint(
            tenant_id=str(tenant_owner.id),
            url="https://example.test/webhook-endpoint",
        )
        session.add(endpoint)
        await session.flush()
        delivery = WebhookDelivery(
            tenant_id=str(tenant_owner.id),
            endpoint_id=endpoint.id,
            event_id="evt-cross-tenant-wh",
            status="failed",
            attempts=1,
            last_status_code=500,
        )
        session.add(delivery)
        await session.commit()
        delivery_id = delivery.id

    await _ensure_global_tenant(slug=tenant_owner.slug, tenant_id=str(tenant_owner.id))
    await _ensure_global_tenant(slug=tenant_other.slug, tenant_id=str(tenant_other.id))

    headers = await make_auth_headers()
    headers["x-tenant"] = str(tenant_other.id)
    response = await async_client.get(
        f"/api/v1/webhooks/deliveries/{delivery_id}/diagnostics",
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_get_document_returns_404_when_document_belongs_to_different_tenant(
    async_client,
    sessionmaker,
    data_factory,
) -> None:
    """JWT и X-Tenant — аренда B; документ создан в A → запрос к БД не находит строку (404), не 403 mismatch."""
    async with sessionmaker() as session:
        tenant_owner = await data_factory.ensure_tenant(slug="doc-iso-owner", session=session)
        tenant_other = await data_factory.ensure_tenant(slug="doc-iso-other", session=session)
        document, _version = await data_factory.create_document(
            tenant=tenant_owner,
            session=session,
        )
        doc_id = document.id
        user_other = await data_factory.create_user(
            tenant=tenant_other,
            role=RoleEnum.ADMIN,
            email="doc-iso-other-admin@example.com",
            session=session,
        )
        await session.commit()
        user_other_id = user_other.id

    await _ensure_global_tenant(slug=tenant_owner.slug, tenant_id=str(tenant_owner.id))
    await _ensure_global_tenant(slug=tenant_other.slug, tenant_id=str(tenant_other.id))

    token = issue_access_token(
        subject=user_other_id,
        tenant=tenant_other.slug,
        role=RoleEnum.ADMIN.value,
        additional_claims={"tenant_id": str(tenant_other.id)},
    )
    headers = {"Authorization": f"Bearer {token}", "x-tenant": str(tenant_other.id)}
    response = await async_client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert response.status_code == 404
