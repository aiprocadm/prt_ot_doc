"""PPE replacement-due notifications.

Mirrors ``contractor_documents.notify_document_expiry``: scan the tenant's
active issues with an expiry date, classify, enqueue one outbox event per
(issue, status, UTC day). Idempotent via the idempotency key + a destination-
agnostic pre-check (see contractor_documents._outbox_key_exists for the why).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.ppe.lifecycle import ISSUE_STATUS_ISSUED
from app.domains.shared import ContingentItemStatus, classify
from app.models.models import Outbox, PPEIssue
from app.services.events import EventType
from app.services.outbox import OutboxService

_NOTIFY_STATUSES = {ContingentItemStatus.DUE_SOON, ContingentItemStatus.OVERDUE}


async def _outbox_key_exists(session: AsyncSession, *, tenant_id: str, key: str) -> bool:
    """Return True if an outbox row already exists for this idempotency key + tenant.

    Deliberately destination-agnostic (unlike ``OutboxService._find_existing``,
    which keys on destination): the row may sit under ``noop://local`` OR a real
    destination — both mean "already emitted today". See the sibling helper in
    ``contractor_documents`` for the full rationale.
    """
    stmt = (
        select(Outbox.id)
        .where(
            Outbox.tenant_id == tenant_id,
            Outbox.idempotency_key == key,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def notify_replacement_due(
    session: AsyncSession, *, tenant_id: str, within_days: int = 30
) -> int:
    """Enqueue PPE_REPLACEMENT_DUE for due-soon/overdue active issues. Returns count."""
    stmt = select(PPEIssue).where(
        PPEIssue.tenant_id == tenant_id,
        PPEIssue.deleted_at.is_(None),
        PPEIssue.status == ISSUE_STATUS_ISSUED,
        PPEIssue.expires_at.is_not(None),
    )
    issues = list((await session.execute(stmt)).scalars().all())

    today = datetime.now(timezone.utc).date()
    outbox = OutboxService(session)
    count = 0
    for issue in issues:
        expiry = classify(issue.expires_at.date(), today, warning_days=within_days)
        if expiry not in _NOTIFY_STATUSES:
            continue
        idem_key = f"ppe-replacement-due:{issue.id}:{expiry.value}:{today.isoformat()}"
        # Pre-check before enqueue so ``count`` reflects genuinely NEW events,
        # not idempotent same-day replays (daily-tick total must be honest).
        if await _outbox_key_exists(session, tenant_id=tenant_id, key=idem_key):
            continue
        await outbox.enqueue(
            tenant_id=tenant_id,
            event_type=EventType.PPE_REPLACEMENT_DUE.value,
            idempotency_key=idem_key,
            payload={
                "tenant_id": tenant_id,
                "ppe_issue_id": issue.id,
                "person_id": issue.person_id,
                "item_id": issue.item_id,
                "item_name": issue.item_name,
                "expires_at": issue.expires_at.isoformat(),
                "status": expiry.value,
            },
        )
        count += 1
    return count
