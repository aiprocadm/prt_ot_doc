"""Domain services for PPE issuance, personal cards and journals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.ppe import lifecycle as lc
from app.modules.ppe.services import NormItem, PPENormService
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
    person = (await session.execute(stmt)).scalar_one_or_none()
    if person is None:
        raise ValueError(f"Person not found: {person_id}")
    return person


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
    item = (await session.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise ValueError(f"PPE item not found: {item_id}")
    return item


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
    certificate_no: str | None = None,
    wear_percent: int | None = None,
    signature_doc_ref: str | None = None,
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
        status=PPEIssueStatus.ISSUED.value,
        certificate_no=certificate_no,
        wear_percent=wear_percent,
        signature_doc_ref=signature_doc_ref,
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


async def _get_issue_record(session: AsyncSession, tenant_id: str, issue_id: str) -> PPEIssue | None:
    stmt = select(PPEIssue).where(
        PPEIssue.id == issue_id,
        PPEIssue.tenant_id == tenant_id,
        PPEIssue.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def return_issue(
    session: AsyncSession,
    *,
    tenant_id: str,
    issue_id: str,
    returned_at: datetime | None = None,
    return_wear_percent: int | None = None,
    signature_doc_ref: str | None = None,
) -> PPEIssue | None:
    """Mark an issue as returned. None when not found; PPETransitionError on FSM violation."""
    issue = await _get_issue_record(session, tenant_id, issue_id)
    if issue is None:
        return None
    lc.validate_transition(str(issue.status), lc.ISSUE_STATUS_RETURNED)
    issue.status = lc.ISSUE_STATUS_RETURNED
    issue.returned_at = returned_at or datetime.now(tz=timezone.utc)
    if return_wear_percent is not None:
        issue.return_wear_percent = return_wear_percent
    if signature_doc_ref is not None:
        issue.signature_doc_ref = signature_doc_ref
    await session.flush()
    await session.refresh(issue)
    return issue


async def writeoff_issue(
    session: AsyncSession,
    *,
    tenant_id: str,
    issue_id: str,
    reason: str,
) -> PPEIssue | None:
    """Write an issue off. None when not found; PPETransitionError on FSM violation."""
    issue = await _get_issue_record(session, tenant_id, issue_id)
    if issue is None:
        return None
    lc.validate_transition(str(issue.status), lc.ISSUE_STATUS_WRITTEN_OFF)
    issue.status = lc.ISSUE_STATUS_WRITTEN_OFF
    issue.writeoff_reason = reason
    await session.flush()
    await session.refresh(issue)
    return issue


async def replace_issue(
    session: AsyncSession,
    *,
    tenant_id: str,
    issue_id: str,
    item_id: str | None = None,
    quantity: int | None = None,
    wear_days: int | None = None,
    expires_at: datetime | None = None,
    certificate_no: str | None = None,
    wear_percent: int | None = None,
    signature_doc_ref: str | None = None,
) -> tuple[PPEIssue, PPEIssue] | None:
    """Close the old issue as replaced and create a linked new one.

    Returns (old, new) or None when the old issue is not found.
    Raises PPETransitionError when the old issue is not active.
    """
    old = await _get_issue_record(session, tenant_id, issue_id)
    if old is None:
        return None
    lc.validate_transition(str(old.status), lc.ISSUE_STATUS_REPLACED)

    new_item_id = item_id or old.item_id
    if new_item_id is None:
        raise ValueError("cannot replace an issue without item_id: specify item_id")

    new = await issue_ppe_item(
        session,
        tenant_id=tenant_id,
        person_id=old.person_id,
        item_id=new_item_id,
        quantity=quantity or old.quantity,
        wear_days=wear_days,
        expires_at=expires_at,
        certificate_no=certificate_no,
        wear_percent=wear_percent,
        signature_doc_ref=signature_doc_ref,
    )
    new.replaces_issue_id = old.id

    old.status = lc.ISSUE_STATUS_REPLACED
    await session.flush()
    await session.refresh(new)
    await session.refresh(old)
    return old, new


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


@dataclass(slots=True)
class CardRequiredLine:
    item_id: str | None
    item_name: str
    required_quantity: int
    interval_days: int | None
    status: str


@dataclass(slots=True)
class CardTimelineEvent:
    occurred_at: datetime
    event: str
    issue_id: str
    item_name: str


@dataclass(slots=True)
class PersonalCard766n:
    person: Person
    position: Position | None
    required: list[CardRequiredLine]
    issues: list[PPEIssue]
    timeline: list[CardTimelineEvent]
    summary_status: str


def _issue_line_key(item_id: str | None, item_name: str) -> str:
    return item_id or f"name:{item_name}"


async def build_personal_card_766n(
    session: AsyncSession, *, tenant_id: str, person_id: str
) -> PersonalCard766n | None:
    """766н personal card: required-by-norms vs issued, with line statuses and timeline.

    Required quantities are the max per catalog item across the position's norms
    (union over hazards). Issues are matched by item_id, with an item_name
    fallback for legacy norms that predate the catalog link.
    """
    stmt = select(Person).where(
        Person.id == person_id,
        Person.tenant_id == tenant_id,
        Person.deleted_at.is_(None),
    )
    person = (await session.execute(stmt)).scalar_one_or_none()
    if person is None:
        return None

    position: Position | None = None
    norms: list[PPENorm] = []
    if person.position_id:
        position = (await session.execute(select(Position).where(
            Position.id == person.position_id,
            Position.tenant_id == tenant_id,
            Position.deleted_at.is_(None),
        ))).scalar_one_or_none()
        norms = list((await session.execute(select(PPENorm).where(
            PPENorm.tenant_id == tenant_id,
            PPENorm.position_id == person.position_id,
        ))).scalars().all())

    issues = list((await session.execute(
        select(PPEIssue).where(
            PPEIssue.tenant_id == tenant_id,
            PPEIssue.person_id == person.id,
            PPEIssue.deleted_at.is_(None),
        ).order_by(PPEIssue.issued_at.asc())
    )).scalars().all())

    # «Положено»: max по позиции каталога через переиспользуемый required_union.
    norm_items = [
        NormItem(
            applies_to_type="position",
            applies_to_id=str(person.position_id),
            ppe_catalog_id=_issue_line_key(norm.item_id, norm.item_name),
            quantity=float(norm.quantity),
            period_months=None,
        )
        for norm in norms
    ]
    required_qty = PPENormService.required_union(
        position_id=str(person.position_id) if person.position_id else None,
        workplace_id=None,
        hazard_ids=set(),
        norm_items=norm_items,
    )
    # Метаданные строки (имя/интервал) — по «лучшей» норме того же ключа.
    line_meta: dict[str, PPENorm] = {}
    for norm in norms:
        key = _issue_line_key(norm.item_id, norm.item_name)
        kept = line_meta.get(key)
        if kept is None or norm.quantity > kept.quantity:
            line_meta[key] = norm

    issues_by_id: dict[str, list[tuple[str, lc.IssueView]]] = {}
    issues_by_name: dict[str, list[tuple[str, lc.IssueView]]] = {}
    for issue in issues:
        view = lc.IssueView(
            quantity=issue.quantity,
            expires_at=issue.expires_at.date() if issue.expires_at else None,
            status=str(issue.status),
        )
        if issue.item_id:
            issues_by_id.setdefault(issue.item_id, []).append((issue.id, view))
        issues_by_name.setdefault(issue.item_name, []).append((issue.id, view))

    def _views_for_line(norm: PPENorm) -> list[lc.IssueView]:
        """Union of id-matched and name-matched issues, deduped by issue id.

        Covers both legacy directions: norm without item_id vs catalog issue,
        and norm with item_id vs legacy issue that predates the catalog link.
        """
        seen: dict[str, lc.IssueView] = {}
        if norm.item_id:
            for issue_id, view in issues_by_id.get(norm.item_id, []):
                seen[issue_id] = view
        for issue_id, view in issues_by_name.get(norm.item_name, []):
            seen.setdefault(issue_id, view)
        return list(seen.values())

    today = datetime.now(tz=timezone.utc).date()
    required: list[CardRequiredLine] = []
    for key, qty in required_qty.items():
        norm = line_meta[key]
        required.append(CardRequiredLine(
            item_id=norm.item_id,
            item_name=norm.item_name,
            required_quantity=int(qty),
            interval_days=norm.interval_days,
            status=lc.card_line_status(int(qty), _views_for_line(norm), today),
        ))
    required.sort(key=lambda line: line.item_name)

    timeline: list[CardTimelineEvent] = []
    for issue in issues:
        timeline.append(CardTimelineEvent(
            occurred_at=issue.issued_at, event="issued",
            issue_id=issue.id, item_name=issue.item_name,
        ))
        current = str(issue.status)
        if current == lc.ISSUE_STATUS_RETURNED and issue.returned_at is not None:
            timeline.append(CardTimelineEvent(
                occurred_at=issue.returned_at, event="returned",
                issue_id=issue.id, item_name=issue.item_name,
            ))
        elif current in (lc.ISSUE_STATUS_WRITTEN_OFF, lc.ISSUE_STATUS_REPLACED, lc.ISSUE_STATUS_LOST):
            timeline.append(CardTimelineEvent(
                occurred_at=issue.updated_at, event=current,
                issue_id=issue.id, item_name=issue.item_name,
            ))
    timeline.sort(key=lambda e: e.occurred_at)

    return PersonalCard766n(
        person=person,
        position=position,
        required=required,
        issues=issues,
        timeline=timeline,
        summary_status=lc.fold_card_status(line.status for line in required),
    )


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

