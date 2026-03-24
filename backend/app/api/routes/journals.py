"""Endpoints for managing safety instruction journals and entries."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_correlation_id, get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.security import AccessContext, abac
from app.domains.ppe import build_journal_export
from app.models.models import Journal, JournalEntry, Person, Tenant
from app.schemas.journal import (
    JournalCreate,
    JournalEntryCreate,
    JournalEntryPage,
    JournalEntryRead,
    JournalEntryUpdate,
    JournalPage,
    JournalRead,
    JournalUpdate,
)
from app.core.permission_checker import PermissionChecker
from app.core.tenant_validation import TenantContextValidator

router = APIRouter(prefix="/journals", tags=["journals"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ManagerAccess = Annotated[
    AccessContext, Depends(abac(_tenant_resource_id, required_roles=["admin"]))
]


async def _get_journal(session: AsyncSession, tenant: Tenant, journal_id: str) -> Journal:
    stmt = select(Journal).where(
        Journal.id == journal_id,
        Journal.tenant_id == tenant.id,
        Journal.deleted_at.is_(None),
    )
    journal = (await session.execute(stmt)).scalar_one_or_none()
    if journal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Journal not found")
    return journal


async def _get_entry(session: AsyncSession, tenant: Tenant, entry_id: str) -> JournalEntry:
    stmt = select(JournalEntry).where(
        JournalEntry.id == entry_id,
        JournalEntry.tenant_id == tenant.id,
        JournalEntry.deleted_at.is_(None),
    )
    entry = (await session.execute(stmt)).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Journal entry not found")
    return entry


async def _ensure_person(session: AsyncSession, tenant: Tenant, person_id: str) -> Person:
    stmt = select(Person).where(
        Person.id == person_id,
        Person.tenant_id == tenant.id,
        Person.deleted_at.is_(None),
    )
    person = (await session.execute(stmt)).scalar_one_or_none()
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")
    return person


def _journal_schema(item: Journal) -> JournalRead:
    if item.metadata_json is None:
        item.metadata_json = {}
    return JournalRead.model_validate(item)


def _entry_schema(item: JournalEntry) -> JournalEntryRead:
    if item.metadata_json is None:
        item.metadata_json = {}
    return JournalEntryRead.model_validate(item)


@router.get("", response_model=JournalPage)
async def list_journals(
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    company_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> JournalPage:
    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = select(Journal).where(Journal.tenant_id == tenant.id, Journal.deleted_at.is_(None))
    if company_id:
        stmt = stmt.where(Journal.company_id == company_id)
    stmt = stmt.order_by(Journal.created_at.desc()).limit(limit).offset(offset)
    items = (await session.execute(stmt)).scalars().all()
    count_stmt = select(func.count()).where(Journal.tenant_id == tenant.id, Journal.deleted_at.is_(None))
    if company_id:
        count_stmt = count_stmt.where(Journal.company_id == company_id)
    total = (await session.execute(count_stmt)).scalar_one()
    return JournalPage(items=[_journal_schema(item) for item in items], total=total)


@router.post("", response_model=JournalRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "journal")
async def create_journal(
    payload: JournalUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
) -> JournalRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    journal = Journal(
        tenant_id=tenant.id,
        company_id=payload.company_id,
        title=payload.title,
        journal_type=payload.journal_type,
        started_at=payload.started_at,
        closed_at=payload.closed_at,
        metadata_json=payload.metadata_json,
    )
    session.add(journal)
    await session.flush()
    await session.refresh(journal)
    return _journal_schema(journal)


@router.get("/{journal_id}", response_model=JournalRead)
async def get_journal(journal_id: str, tenant: TenantDep, session: SessionDep, access: ManagerAccess,
    correlation_id: str = Depends(get_correlation_id)) -> JournalRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    journal = await _get_journal(session, tenant, journal_id)
    return _journal_schema(journal)


@router.patch("/{journal_id}", response_model=JournalRead)
@audit_operation("update", "journal")
async def update_journal(
    journal_id: str,
    payload: JournalUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
) -> JournalRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    journal = await _get_journal(session, tenant, journal_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(journal, field, value)
    await session.flush()
    await session.refresh(journal)
    return _journal_schema(journal)


@router.delete("/{journal_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
@audit_operation("delete", "journal")
async def delete_journal(
    journal_id: str, tenant: TenantDep, session: SessionDep, access: ManagerAccess
) -> None:
    TenantContextValidator.ensure_tenant_context(tenant)

    journal = await _get_journal(session, tenant, journal_id)
    if journal.deleted_at is None:
        journal.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{journal_id}/entries", response_model=JournalEntryPage)
async def list_entries(
    journal_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    person_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> JournalEntryPage:
    TenantContextValidator.ensure_tenant_context(tenant)

    await _get_journal(session, tenant, journal_id)
    stmt = select(JournalEntry).where(
        JournalEntry.tenant_id == tenant.id,
        JournalEntry.journal_id == journal_id,
        JournalEntry.deleted_at.is_(None),
    )
    if person_id:
        stmt = stmt.where(JournalEntry.person_id == person_id)
    stmt = stmt.order_by(JournalEntry.entry_date.desc()).limit(limit).offset(offset)
    items = (await session.execute(stmt)).scalars().all()
    count_stmt = select(func.count()).where(
        JournalEntry.tenant_id == tenant.id,
        JournalEntry.journal_id == journal_id,
        JournalEntry.deleted_at.is_(None),
    )
    if person_id:
        count_stmt = count_stmt.where(JournalEntry.person_id == person_id)
    total = (await session.execute(count_stmt)).scalar_one()
    return JournalEntryPage(items=[_entry_schema(item) for item in items], total=total)


@router.post("/{journal_id}/entries", response_model=JournalEntryRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "journal_entry")
async def create_entry(
    journal_id: str,
    payload: JournalEntryUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
) -> JournalEntryRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    journal = await _get_journal(session, tenant, journal_id)
    person = await _ensure_person(session, tenant, payload.person_id)
    entry_date = payload.entry_date or date.today()
    entry = JournalEntry(
        tenant_id=tenant.id,
        journal_id=journal.id,
        person_id=person.id,
        entry_type=payload.entry_type,
        entry_date=entry_date,
        instructor=payload.instructor,
        notes=payload.notes,
        metadata_json=payload.metadata_json,
    )
    session.add(entry)
    await session.flush()
    await session.refresh(entry)
    return _entry_schema(entry)


@router.get("/entries/{entry_id}", response_model=JournalEntryRead)
async def get_entry(
    entry_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    correlation_id: str = Depends(get_correlation_id),
) -> JournalEntryRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    entry = await _get_entry(session, tenant, entry_id)
    return _entry_schema(entry)


@router.patch("/entries/{entry_id}", response_model=JournalEntryRead)
@audit_operation("update", "journal_entry")
async def update_entry(
    entry_id: str,
    payload: JournalEntryUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
) -> JournalEntryRead:
    entry = await _get_entry(session, tenant, entry_id)
    updates = payload.model_dump(exclude_unset=True)
    if "person_id" in updates and updates["person_id"] is not None:
        await _ensure_person(session, tenant, updates["person_id"])
    if "journal_id" in updates and updates["journal_id"] is not None:
        await _get_journal(session, tenant, updates["journal_id"])
    for field, value in updates.items():
        if field == "entry_date" and value is None:
            value = entry.entry_date
        setattr(entry, field, value)
    await session.flush()
    await session.refresh(entry)
    return _entry_schema(entry)


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
@audit_operation("delete", "journal_entry")
async def delete_entry(entry_id: str, tenant: TenantDep, session: SessionDep, access: ManagerAccess,
    correlation_id: str = Depends(get_correlation_id)) -> None:
    TenantContextValidator.ensure_tenant_context(tenant)

    entry = await _get_entry(session, tenant, entry_id)
    if entry.deleted_at is None:
        entry.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{journal_id}/export", response_model=dict)
async def export_journal(
    journal_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
) -> dict[str, object]:
    TenantContextValidator.ensure_tenant_context(tenant)

    payload = await build_journal_export(session, tenant_id=tenant.id, journal_id=journal_id)
    journal = payload.get("journal")
    entries = payload.get("entries", [])
    return {
        "journal": _journal_schema(journal),
        "entries": [_entry_schema(item) for item in entries],
    }

