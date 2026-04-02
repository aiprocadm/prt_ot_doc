"""Domain services for PPE issuance, personal cards and journals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Journal,
    JournalEntry,
    Person,
    Position,
    PPEIssue,
    PPEIssueStatus,
    PPEItem,
    PPENorm,
)


@dataclass(slots=True)
class PPEPersonalCard:
    person: Person
    position: Position | None
    norms: list[PPENorm]
    issues: list[PPEIssue]


async def _get_person(session: AsyncSession, tenant_id: str, person_id: str) -> Person:
    stmt = select(Person).where(
        Person.id == person_id,
        Person.tenant_id == tenant_id,
        Person.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one()


async def _get_position(session: AsyncSession, tenant_id: str, position_id: str) -> Position:
    stmt = select(Position).where(
        Position.id == position_id,
        Position.tenant_id == tenant_id,
        Position.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one()


async def _get_ppe_item(session: AsyncSession, tenant_id: str, item_id: str) -> PPEItem:
    stmt = select(PPEItem).where(
        PPEItem.id == item_id,
        PPEItem.tenant_id == tenant_id,
        PPEItem.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one()


async def issue_ppe_item(
    session: AsyncSession,
    *,
    tenant_id: str,
    person_id: str,
    item_id: str,
    quantity: int = 1,
    issued_at: datetime | None = None,
    wear_days: int | None = None,
    expires_at: datetime | None = None,
) -> PPEIssue:
    """Issue a PPE item to a person and compute expiration."""

    person = await _get_person(session, tenant_id, person_id)
    item = await _get_ppe_item(session, tenant_id, item_id)
    issued_value = issued_at or datetime.now(tz=timezone.utc)
    wear_value = wear_days or item.default_wear_days
    expires_value = expires_at
    if expires_value is None and wear_value:
        expires_value = issued_value + timedelta(days=wear_value)

    record = PPEIssue(
        tenant_id=tenant_id,
        person_id=person.id,
        item_id=item.id,
        item_name=item.name,
        quantity=max(1, quantity),
        issued_at=issued_value,
        expires_at=expires_value,
        wear_days=wear_value,
        status=PPEIssueStatus.ISSUED,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def list_expiring_issues(
    session: AsyncSession,
    *,
    tenant_id: str,
    within_days: int,
    reference: datetime | None = None,
) -> list[PPEIssue]:
    """Return PPE issues that will expire within the given period."""

    now = reference or datetime.now(tz=timezone.utc)
    horizon = now + timedelta(days=within_days)
    stmt = select(PPEIssue).where(
        PPEIssue.tenant_id == tenant_id,
        PPEIssue.deleted_at.is_(None),
        PPEIssue.status == PPEIssueStatus.ISSUED,
        PPEIssue.expires_at.is_not(None),
        PPEIssue.expires_at <= horizon,
        PPEIssue.expires_at >= now,
    )
    return (await session.execute(stmt)).scalars().all()


async def build_personal_card_payload(
    session: AsyncSession, *, tenant_id: str, person_id: str
) -> PPEPersonalCard:
    """Aggregate norms and issues for templating of a personal PPE card."""

    person = await _get_person(session, tenant_id, person_id)
    position: Position | None = None
    norms: list[PPENorm] = []
    if person.position_id:
        position = await _get_position(session, tenant_id, person.position_id)
        norm_stmt = select(PPENorm).where(
            PPENorm.tenant_id == tenant_id,
            PPENorm.position_id == position.id,
        )
        norms = (await session.execute(norm_stmt)).scalars().all()

    issue_stmt = select(PPEIssue).where(
        PPEIssue.tenant_id == tenant_id,
        PPEIssue.person_id == person.id,
        PPEIssue.deleted_at.is_(None),
    )
    issues = (await session.execute(issue_stmt)).scalars().all()
    return PPEPersonalCard(person=person, position=position, norms=list(norms), issues=list(issues))


async def build_journal_export(
    session: AsyncSession, *, tenant_id: str, journal_id: str
) -> dict[str, object]:
    """Prepare payload for rendering a journal with entries."""

    journal_stmt = select(Journal).where(
        Journal.id == journal_id,
        Journal.tenant_id == tenant_id,
        Journal.deleted_at.is_(None),
    )
    journal = (await session.execute(journal_stmt)).scalar_one()
    entries_stmt = (
        select(JournalEntry)
        .where(
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.journal_id == journal.id,
            JournalEntry.deleted_at.is_(None),
        )
        .order_by(JournalEntry.entry_date.asc())
    )
    entries = (await session.execute(entries_stmt)).scalars().all()

    return {
        "journal": journal,
        "entries": list(entries),
    }

