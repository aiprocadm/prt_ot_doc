"""Cross-domain reactions (document lifecycle → universal tasks, timeline).

Wave 3 / TZ: automatic links between document core and operational task inbox.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.obligations import Task, TaskPriority, TaskStatus

logger = logging.getLogger(__name__)

# Stable title for idempotent "one open follow-up per signed document"
_SIGNED_DOC_FOLLOWUP_TITLE = "Signed document: verify distribution and archive policy"


async def on_document_signed_create_followup_task(
    session: AsyncSession,
    *,
    document: Document,
    actor_id: str | None,
) -> None:
    """When a document becomes SIGNED, ensure an open operational task exists for follow-up."""

    tenant_id = str(document.tenant_id)
    existing = (
        await session.execute(
            select(Task.id)
            .where(
                Task.tenant_id == tenant_id,
                Task.entity_type == "document",
                Task.entity_id == document.id,
                Task.status == TaskStatus.OPEN,
                Task.title == _SIGNED_DOC_FOLLOWUP_TITLE,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return

    due = datetime.now(tz=timezone.utc) + timedelta(days=7)
    assignee = actor_id or document.created_by
    task = Task(
        tenant_id=tenant_id,
        title=_SIGNED_DOC_FOLLOWUP_TITLE,
        description=(
            "Cross-domain follow-up: confirm internal distribution, retention, and linked "
            f"obligations for document {document.id}."
        ),
        entity_type="document",
        entity_id=document.id,
        due_at=due,
        status=TaskStatus.OPEN,
        priority=TaskPriority.MEDIUM,
        assignee_id=assignee,
        created_by=actor_id,
    )
    session.add(task)
    await session.flush()
    logger.info(
        "domain_hooks.document_signed_followup_task",
        extra={
            "tenant_id": tenant_id,
            "document_id": document.id,
            "task_id": task.id,
            "assignee_id": assignee,
        },
    )
