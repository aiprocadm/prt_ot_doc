"""Contractor-document expiry notifications.

Mirrors ``notify_readiness`` (contractor_admission.py): load tenant documents that
carry a ``valid_until``, classify, enqueue an outbox event for DUE_SOON / OVERDUE.
Idempotent per (document, status, UTC date).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.contractors.documents import document_expiry_status
from app.domains.shared import ContingentItemStatus
from app.models.models import Outbox
from app.modules.contractors.models import ContractorDocument
from app.services.events import EventType
from app.services.outbox import OutboxService

_STATUS_EVENT = {
    ContingentItemStatus.DUE_SOON: EventType.CONTRACTOR_DOCUMENT_EXPIRING,
    ContingentItemStatus.OVERDUE: EventType.CONTRACTOR_DOCUMENT_EXPIRED,
}


async def _outbox_key_exists(session: AsyncSession, *, tenant_id: str, key: str) -> bool:
    """Return True if an outbox row already exists for this idempotency key + tenant.

    Deliberately destination-agnostic (unlike ``OutboxService._find_existing``, which
    keys on destination): the row may have been stored under ``noop://local`` (tenant
    without webhook destinations) OR under a real destination — both must count as
    "already emitted today". A destination-scoped check would over-count in the
    has-destinations regime.
    """
    stmt = (
        select(Outbox.id)
        .where(
            Outbox.tenant_id == tenant_id,
            Outbox.idempotency_key == key,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def notify_document_expiry(session: AsyncSession, *, tenant_id: str) -> int:
    """Enqueue expiry events for the tenant's documents. Returns count enqueued."""
    stmt = select(ContractorDocument).where(
        ContractorDocument.tenant_id == tenant_id,
        ContractorDocument.deleted_at.is_(None),
        ContractorDocument.valid_until.is_not(None),
    )
    documents = list((await session.execute(stmt)).scalars().all())

    today = datetime.now(timezone.utc).date()
    outbox = OutboxService(session)
    count = 0
    for doc in documents:
        expiry = document_expiry_status(doc.valid_until, today)
        event_type = _STATUS_EVENT.get(expiry)
        if event_type is None:
            continue
        idem_key = f"contractor-document:{doc.id}:{expiry.value}:{today.isoformat()}"
        # Pre-check before enqueue so ``count`` reflects genuinely NEW events, not
        # idempotent same-day replays. (Sibling notify_readiness lacks this and would
        # over-count on a re-run; here the daily-tick total must be honest.)
        if await _outbox_key_exists(session, tenant_id=tenant_id, key=idem_key):
            continue
        await outbox.enqueue(
            tenant_id=tenant_id,
            event_type=event_type.value,
            idempotency_key=idem_key,
            payload={
                "tenant_id": tenant_id,
                "metadata": {
                    "document_id": doc.id,
                    "contractor_id": doc.contractor_id,
                    "employee_id": doc.employee_id,
                    "doc_type": doc.doc_type,
                    "valid_until": doc.valid_until.isoformat(),
                    "status": expiry.value,
                },
            },
        )
        count += 1
    return count
