from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.security import rbac
from app.models.models import (
    BriefingEntry,
    BriefingJournal,
    BriefingSignature,
    BriefingTemplate,
    Tenant,
)
from app.modules.briefings.services import (
    BriefingEntryService,
    BriefingSignatureConflict,
    NoPendingCodeRequest,
)
from app.modules.rbac_abac import require_permission
from app.services.audit import AuditService
from app.services.pep_signing import PepConflict

_BRIEFINGS_READ_PERMISSION = "briefings.read"
_BRIEFINGS_WRITE_PERMISSION = "briefings.update"
_BRIEFINGS_CREATE_PERMISSION = "briefings.create"

router = APIRouter(prefix="/briefings", tags=["briefings"], dependencies=[Depends(rbac())])
_PermReadDep = Depends(require_permission(_BRIEFINGS_READ_PERMISSION))
_PermWriteDep = Depends(require_permission(_BRIEFINGS_WRITE_PERMISSION))
_PermCreateDep = Depends(require_permission(_BRIEFINGS_CREATE_PERMISSION))


class BriefingTemplatePayload(BaseModel):
    code: str
    title: str
    briefing_type: str
    status: str = "draft"
    description: str | None = None
    validity_days: int | None = None
    require_signature_code: bool = False


class BriefingJournalPayload(BaseModel):
    code: str
    title: str
    site_id: str | None = None
    department_id: str | None = None
    journal_type: str
    status: str = "active"


class BriefingEntryPayload(BaseModel):
    # _entry_read() round-trips a BriefingEntry ORM object through this model
    # (BriefingEntryPayload.model_validate(entry)); without from_attributes that
    # raises a pydantic model_type error -> 400 on every entry create.
    model_config = ConfigDict(from_attributes=True)

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


class BriefingConfirmCodePayload(BaseModel):
    code: str


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


async def _audit(
    session: AsyncSession,
    request: Request,
    *,
    tenant_id: str,
    action: str,
    object_type: str,
    object_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    await AuditService(session).log_event(
        tenant_id=tenant_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        ip=request.client.host if request.client else "unknown",
        details=details or {},
    )


def _briefing_bad_request(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=api_problem_detail(
            code="BRIEFING_VALIDATION_ERROR", message=message, error_type="briefings"
        ),
    )


def _briefing_signature_conflict(message: str) -> HTTPException:
    """Гонка дублей подписи (unique-индекс ed03) → честный 409, не 500."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code="BRIEFING_SIGNATURE_CONFLICT", message=message, error_type="briefings"
        ),
    )


def _briefing_conflict(code: str, message: str) -> HTTPException:
    """Явные конфликты сервис-слоя (PEP_CONFLICT / NO_PENDING_CODE_REQUEST); в отличие от _briefing_signature_conflict не связан с гонкой unique-индекса."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(code=code, message=message, error_type="briefings"),
    )


def _entry_read(
    entry: BriefingEntry, signatures: list[BriefingSignature] | None = None
) -> BriefingEntryRead:
    resolved_signatures = signatures or []
    valid_until = getattr(entry, "valid_until", None)
    return BriefingEntryRead(
        **BriefingEntryPayload.model_validate(entry).model_dump(),
        id=str(entry.id),
        signatures=[BriefingSignatureRead.model_validate(item) for item in resolved_signatures],
        is_overdue=bool(
            valid_until and valid_until < datetime.now(timezone.utc) and entry.status != "completed"
        ),
    )


@router.get("/templates", response_model=BriefingCollection)
async def list_templates(
    request: Request,
    response: Response,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _PermReadDep,
):
    items = list(
        (
            await session.execute(
                select(BriefingTemplate).where(
                    BriefingTemplate.tenant_id == tenant.id, BriefingTemplate.deleted_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[("total", len(items)), ("kind", "templates")],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return BriefingCollection(
        items=[BriefingTemplateRead.model_validate(item) for item in items], total=len(items)
    )


@router.post("/templates", response_model=BriefingTemplateRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "briefing_template")
async def create_template(
    payload: BriefingTemplatePayload,
    request: Request,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _PermCreateDep,
):
    item = BriefingTemplate(tenant_id=tenant.id, **payload.model_dump())
    session.add(item)
    await session.flush()
    await session.commit()
    return BriefingTemplateRead.model_validate(item)


@router.patch("/templates/{item_id}", response_model=BriefingTemplateRead)
@audit_operation("update", "briefing_template")
async def patch_template(
    item_id: str,
    payload: BriefingTemplatePayload,
    request: Request,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _PermWriteDep,
):
    item = await session.get(BriefingTemplate, item_id)
    if not item or item.tenant_id != tenant.id or item.deleted_at is not None:
        raise HTTPException(404, "Template not found")
    for k, v in payload.model_dump().items():
        setattr(item, k, v)
    await session.commit()
    return BriefingTemplateRead.model_validate(item)


@router.get("/journals", response_model=BriefingCollection)
async def list_journals(
    request: Request,
    response: Response,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _PermReadDep,
):
    items = list(
        (
            await session.execute(
                select(BriefingJournal).where(
                    BriefingJournal.tenant_id == tenant.id, BriefingJournal.deleted_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[("total", len(items)), ("kind", "journals")],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return BriefingCollection(
        items=[BriefingJournalRead.model_validate(item) for item in items], total=len(items)
    )


@router.post("/journals", response_model=BriefingJournalRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "briefing_journal")
async def create_journal(
    payload: BriefingJournalPayload,
    request: Request,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _PermCreateDep,
):
    item = BriefingJournal(tenant_id=tenant.id, **payload.model_dump())
    session.add(item)
    await session.flush()
    await session.commit()
    return BriefingJournalRead.model_validate(item)


@router.get("/entries", response_model=BriefingCollection)
async def list_entries(
    request: Request,
    response: Response,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _PermReadDep,
):
    items = list(
        (
            await session.execute(
                select(BriefingEntry)
                .where(BriefingEntry.tenant_id == tenant.id, BriefingEntry.deleted_at.is_(None))
                .order_by(BriefingEntry.briefing_date.desc())
            )
        )
        .scalars()
        .all()
    )
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[("total", len(items)), ("kind", "entries")],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    signatures = (
        (
            await session.execute(
                select(BriefingSignature).where(BriefingSignature.tenant_id == tenant.id)
            )
        )
        .scalars()
        .all()
    )
    grouped: dict[str, list[BriefingSignature]] = {}
    for signature in signatures:
        grouped.setdefault(str(signature.briefing_entry_id), []).append(signature)
    return BriefingCollection(
        items=[_entry_read(item, grouped.get(str(item.id), [])) for item in items], total=len(items)
    )


@router.get("/entries/overdue", response_model=BriefingCollection)
async def list_overdue_entries(
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _PermReadDep,
):
    service = BriefingEntryService()
    items = await service.list_overdue(session, tenant_id=str(tenant.id))
    return BriefingCollection(items=[_entry_read(item) for item in items], total=len(items))


@router.post("/entries", response_model=BriefingEntryRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "briefing_entry")
async def create_entry(
    payload: BriefingEntryPayload,
    request: Request,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _PermCreateDep,
):
    item = BriefingEntry(tenant_id=tenant.id, **payload.model_dump())
    session.add(item)
    await session.flush()
    await session.commit()
    return _entry_read(item)


@router.post("/entries/bulk-create", response_model=BriefingCollection)
async def bulk_create_entries(
    payload: BriefingBulkCreatePayload,
    request: Request,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _PermCreateDep,
):
    created = []
    # ``person_id`` is inherited from BriefingEntryPayload; exclude it too, else it
    # collides with the explicit per-person ``person_id`` below (TypeError: got
    # multiple values for keyword argument 'person_id').
    base = payload.model_dump(exclude={"person_ids", "person_id"})
    for person_id in payload.person_ids:
        entry = BriefingEntry(tenant_id=tenant.id, person_id=person_id, **base)
        session.add(entry)
        created.append(entry)
    await session.flush()
    for entry in created:
        await _audit(
            session,
            request,
            tenant_id=str(tenant.id),
            action="create",
            object_type="briefing_entry",
            object_id=entry.id,
            details={"bulk": True, "person_id": entry.person_id},
        )
    await session.commit()
    return BriefingCollection(items=[_entry_read(item) for item in created], total=len(created))


@router.post("/entries/{item_id}/sign-employee")
@audit_operation("sign_employee", "briefing_entry", id_attr="entry")
async def sign_employee(
    item_id: str,
    payload: BriefingSignPayload,
    request: Request,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _PermWriteDep,
):
    item = await session.get(BriefingEntry, item_id)
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(404, "Entry not found")
    svc = BriefingEntryService()
    if await svc.requires_signature_code(session, item):
        try:
            req, code = await svc.start_employee_signature(session, item, payload.signer_user_id)
        except PepConflict as exc:
            await session.commit()
            raise _briefing_conflict("PEP_CONFLICT", str(exc)) from exc
        await session.commit()
        # confirm_code возвращается оформителю намеренно — единственная точка
        # видимости разового кода (прод-доставка работнику OOB: SMS/печать).
        # Зеркало контракта документов (см. spec §1/§6).
        return {
            "entry": _entry_read(item),
            "pending": {"pep_request_id": req.id, "status": req.status, "confirm_code": code},
        }
    try:
        sig = await svc.sign(
            session,
            item,
            "employee",
            payload.signer_user_id,
            signature_payload=payload.signature_payload,
        )
    except BriefingSignatureConflict as exc:
        raise _briefing_signature_conflict(str(exc)) from exc
    await session.commit()
    return {
        "entry": _entry_read(item, [sig]),
        "signature": BriefingSignatureRead.model_validate(sig),
    }


@router.post("/entries/{item_id}/confirm-code")
@audit_operation("confirm_code", "briefing_entry", id_attr="entry")
async def confirm_code(
    item_id: str,
    payload: BriefingConfirmCodePayload,
    request: Request,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _PermWriteDep,
):
    item = await session.get(BriefingEntry, item_id)
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(404, "Entry not found")
    svc = BriefingEntryService()
    try:
        sig = await svc.confirm_code(session, item, payload.code)
    except NoPendingCodeRequest as exc:
        raise _briefing_conflict("NO_PENDING_CODE_REQUEST", str(exc)) from exc
    except PepConflict as exc:
        # commit-on-conflict: счётчик попыток / expired / declined должны сохраниться
        await session.commit()
        raise _briefing_conflict("PEP_CONFLICT", str(exc)) from exc
    except BriefingSignatureConflict as exc:
        raise _briefing_signature_conflict(str(exc)) from exc
    await session.commit()
    return {
        "entry": _entry_read(item, [sig]),
        "signature": BriefingSignatureRead.model_validate(sig),
    }


@router.post("/entries/{item_id}/sign-instructor")
@audit_operation("sign_instructor", "briefing_entry", id_attr="entry")
async def sign_instructor(
    item_id: str,
    payload: BriefingSignPayload,
    request: Request,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _PermWriteDep,
):
    item = await session.get(BriefingEntry, item_id)
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(404, "Entry not found")
    try:
        sig = await BriefingEntryService().sign(
            session,
            item,
            "instructor",
            payload.signer_user_id,
            signature_payload=payload.signature_payload,
        )
    except BriefingSignatureConflict as exc:
        raise _briefing_signature_conflict(str(exc)) from exc
    await session.commit()
    return {
        "entry": _entry_read(item, [sig]),
        "signature": BriefingSignatureRead.model_validate(sig),
    }


@router.post("/entries/{item_id}/complete", response_model=BriefingEntryRead)
@audit_operation("complete", "briefing_entry")
async def complete_entry(
    item_id: str,
    request: Request,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _PermWriteDep,
):
    item = await session.get(BriefingEntry, item_id)
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(404, "Entry not found")
    try:
        result = await BriefingEntryService().complete(session, item)
    except ValueError as exc:
        raise _briefing_bad_request(str(exc)) from exc
    signatures = (
        (
            await session.execute(
                select(BriefingSignature).where(BriefingSignature.briefing_entry_id == item.id)
            )
        )
        .scalars()
        .all()
    )
    await session.commit()
    return _entry_read(result, list(signatures))


@router.post("/entries/remind-overdue")
async def remind_overdue_entries(
    request: Request,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _PermWriteDep,
):
    service = BriefingEntryService()
    overdue = await service.notify_overdue(session, tenant_id=str(tenant.id))
    await _audit(
        session,
        request,
        tenant_id=str(tenant.id),
        action="notify_overdue",
        object_type="briefing_entry",
        object_id="bulk",
        details={"count": len(overdue)},
    )
    await session.commit()
    return {"count": len(overdue), "items": [_entry_read(item) for item in overdue]}
