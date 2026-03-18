from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from app.api.dependencies import get_session, get_tenant_record
from app.models.models import BriefingEntry, BriefingJournal, BriefingSignature, BriefingTemplate, Tenant
from app.modules.briefings.services import BriefingEntryService
from app.services.audit import AuditService
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/briefings", tags=["briefings"])


class BriefingTemplatePayload(BaseModel):
    code: str
    title: str
    briefing_type: str
    status: str = "draft"
    description: str | None = None
    validity_days: int | None = None


class BriefingJournalPayload(BaseModel):
    code: str
    title: str
    site_id: str | None = None
    department_id: str | None = None
    journal_type: str
    status: str = "active"


class BriefingEntryPayload(BaseModel):
    briefing_journal_id: str
    briefing_template_id: str | None = None
    person_id: str | None = None
    instructor_user_id: str | None = None
    site_id: str | None = None
    department_id: str | None = None
    workplace_id: str | None = None
    briefing_type: str
    briefing_date: datetime
    valid_until: datetime | None = None
    reason: str | None = None
    status: str = "draft"
    notes: str | None = None


class BriefingSignPayload(BaseModel):
    signer_user_id: str | None = None
    signature_payload: dict[str, Any] = Field(default_factory=dict)


class BriefingBulkCreatePayload(BriefingEntryPayload):
    person_ids: list[str] = Field(default_factory=list)


class BriefingTemplateRead(BriefingTemplatePayload):
    model_config = ConfigDict(from_attributes=True)
    id: str


class BriefingJournalRead(BriefingJournalPayload):
    model_config = ConfigDict(from_attributes=True)
    id: str


class BriefingSignatureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    signer_type: str
    signer_user_id: str | None = None
    signature_mode: str
    signed_at: datetime
    signature_payload: dict[str, Any] | None = None


class BriefingEntryRead(BriefingEntryPayload):
    model_config = ConfigDict(from_attributes=True)
    id: str
    signatures: list[BriefingSignatureRead] = Field(default_factory=list)
    is_overdue: bool = False


class BriefingCollection(BaseModel):
    items: list[Any]
    total: int


async def _audit(session: AsyncSession, request: Request, *, tenant_id: str, action: str, object_type: str, object_id: str, details: dict[str, Any] | None = None) -> None:
    await AuditService(session).log_event(
        tenant_id=tenant_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        ip=request.client.host if request.client else "unknown",
        details=details or {},
    )


def _entry_read(entry: BriefingEntry, signatures: list[BriefingSignature] | None = None) -> BriefingEntryRead:
    resolved_signatures = signatures or []
    valid_until = getattr(entry, "valid_until", None)
    return BriefingEntryRead(
        **BriefingEntryPayload.model_validate(entry).model_dump(),
        id=str(entry.id),
        signatures=[BriefingSignatureRead.model_validate(item) for item in resolved_signatures],
        is_overdue=bool(valid_until and valid_until < datetime.now(timezone.utc) and entry.status != "completed"),
    )


@router.get("/templates", response_model=BriefingCollection)
async def list_templates(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    items = (await session.execute(select(BriefingTemplate).where(BriefingTemplate.tenant_id == tenant.id, BriefingTemplate.deleted_at.is_(None)))).scalars().all()
    return BriefingCollection(items=[BriefingTemplateRead.model_validate(item) for item in items], total=len(items))


@router.post("/templates", response_model=BriefingTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(payload: BriefingTemplatePayload, request: Request, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = BriefingTemplate(tenant_id=tenant.id, **payload.model_dump())
    session.add(item)
    await session.flush()
    await _audit(session, request, tenant_id=str(tenant.id), action="create", object_type="briefing_template", object_id=item.id, details={"briefing_type": item.briefing_type})
    await session.commit()
    return BriefingTemplateRead.model_validate(item)


@router.patch("/templates/{item_id}", response_model=BriefingTemplateRead)
async def patch_template(item_id: str, payload: BriefingTemplatePayload, request: Request, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await session.get(BriefingTemplate, item_id)
    if not item or item.tenant_id != tenant.id or item.deleted_at is not None:
        raise HTTPException(404, "Template not found")
    for k, v in payload.model_dump().items():
        setattr(item, k, v)
    await _audit(session, request, tenant_id=str(tenant.id), action="update", object_type="briefing_template", object_id=item.id)
    await session.commit()
    return BriefingTemplateRead.model_validate(item)


@router.get("/journals", response_model=BriefingCollection)
async def list_journals(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    items = (await session.execute(select(BriefingJournal).where(BriefingJournal.tenant_id == tenant.id, BriefingJournal.deleted_at.is_(None)))).scalars().all()
    return BriefingCollection(items=[BriefingJournalRead.model_validate(item) for item in items], total=len(items))


@router.post("/journals", response_model=BriefingJournalRead, status_code=status.HTTP_201_CREATED)
async def create_journal(payload: BriefingJournalPayload, request: Request, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = BriefingJournal(tenant_id=tenant.id, **payload.model_dump())
    session.add(item)
    await session.flush()
    await _audit(session, request, tenant_id=str(tenant.id), action="create", object_type="briefing_journal", object_id=item.id, details={"journal_type": item.journal_type})
    await session.commit()
    return BriefingJournalRead.model_validate(item)


@router.get("/entries", response_model=BriefingCollection)
async def list_entries(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    items = (await session.execute(select(BriefingEntry).where(BriefingEntry.tenant_id == tenant.id, BriefingEntry.deleted_at.is_(None)).order_by(BriefingEntry.briefing_date.desc()))).scalars().all()
    signatures = (await session.execute(select(BriefingSignature).where(BriefingSignature.tenant_id == tenant.id))).scalars().all()
    grouped: dict[str, list[BriefingSignature]] = {}
    for signature in signatures:
        grouped.setdefault(str(signature.briefing_entry_id), []).append(signature)
    return BriefingCollection(items=[_entry_read(item, grouped.get(str(item.id), [])) for item in items], total=len(items))


@router.get("/entries/overdue", response_model=BriefingCollection)
async def list_overdue_entries(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    service = BriefingEntryService()
    items = await service.list_overdue(session, tenant_id=str(tenant.id))
    return BriefingCollection(items=[_entry_read(item) for item in items], total=len(items))


@router.post("/entries", response_model=BriefingEntryRead, status_code=status.HTTP_201_CREATED)
async def create_entry(payload: BriefingEntryPayload, request: Request, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = BriefingEntry(tenant_id=tenant.id, **payload.model_dump())
    session.add(item)
    await session.flush()
    await _audit(session, request, tenant_id=str(tenant.id), action="create", object_type="briefing_entry", object_id=item.id, details={"briefing_type": item.briefing_type, "person_id": item.person_id})
    await session.commit()
    return _entry_read(item)


@router.post("/entries/bulk-create", response_model=BriefingCollection)
async def bulk_create_entries(payload: BriefingBulkCreatePayload, request: Request, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    created = []
    base = payload.model_dump(exclude={"person_ids"})
    for person_id in payload.person_ids:
        entry = BriefingEntry(tenant_id=tenant.id, person_id=person_id, **base)
        session.add(entry)
        created.append(entry)
    await session.flush()
    for entry in created:
        await _audit(session, request, tenant_id=str(tenant.id), action="create", object_type="briefing_entry", object_id=entry.id, details={"bulk": True, "person_id": entry.person_id})
    await session.commit()
    return BriefingCollection(items=[_entry_read(item) for item in created], total=len(created))


@router.post("/entries/{item_id}/sign-employee")
async def sign_employee(item_id: str, payload: BriefingSignPayload, request: Request, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await session.get(BriefingEntry, item_id)
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(404, "Entry not found")
    sig = await BriefingEntryService().sign(session, item, "employee", payload.signer_user_id, signature_payload=payload.signature_payload)
    await _audit(session, request, tenant_id=str(tenant.id), action="sign_employee", object_type="briefing_entry", object_id=item.id)
    await session.commit()
    return {"entry": _entry_read(item, [sig]), "signature": BriefingSignatureRead.model_validate(sig)}


@router.post("/entries/{item_id}/sign-instructor")
async def sign_instructor(item_id: str, payload: BriefingSignPayload, request: Request, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await session.get(BriefingEntry, item_id)
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(404, "Entry not found")
    sig = await BriefingEntryService().sign(session, item, "instructor", payload.signer_user_id, signature_payload=payload.signature_payload)
    await _audit(session, request, tenant_id=str(tenant.id), action="sign_instructor", object_type="briefing_entry", object_id=item.id)
    await session.commit()
    return {"entry": _entry_read(item, [sig]), "signature": BriefingSignatureRead.model_validate(sig)}


@router.post("/entries/{item_id}/complete", response_model=BriefingEntryRead)
async def complete_entry(item_id: str, request: Request, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await session.get(BriefingEntry, item_id)
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(404, "Entry not found")
    try:
        result = await BriefingEntryService().complete(session, item)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    signatures = (await session.execute(select(BriefingSignature).where(BriefingSignature.briefing_entry_id == item.id))).scalars().all()
    await _audit(session, request, tenant_id=str(tenant.id), action="complete", object_type="briefing_entry", object_id=item.id, details={"valid_until": result.valid_until.isoformat() if result.valid_until else None})
    await session.commit()
    return _entry_read(result, list(signatures))


@router.post("/entries/remind-overdue")
async def remind_overdue_entries(request: Request, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    service = BriefingEntryService()
    overdue = await service.notify_overdue(session, tenant_id=str(tenant.id))
    await _audit(session, request, tenant_id=str(tenant.id), action="notify_overdue", object_type="briefing_entry", object_id="bulk", details={"count": len(overdue)})
    await session.commit()
    return {"count": len(overdue), "items": [_entry_read(item) for item in overdue]}
