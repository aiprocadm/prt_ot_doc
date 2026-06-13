"""PEP signing API (vNext §6.9): внутренняя простая электронная подпись."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.deps.tracing import get_trace_id
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, abac
from app.models.models import SignatureRequest, Tenant
from app.services.pep_signing import (
    PepApprovalRequired,
    PepConflict,
    PepForbidden,
    PepNotFound,
    PepSigningService,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    value = getattr(tenant, "id", None)
    return str(value) if value is not None else None


_PEP_READ_ROLES = ["admin", "employee"]
_PEP_WRITE_ROLES = ["admin", "employee"]

ReaderAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_PEP_READ_ROLES, action="read pep signing")),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(
        abac(_tenant_resource_id, required_roles=_PEP_WRITE_ROLES, action="manage pep signing")
    ),
]


def _correlation_id(request: Request, response: Response) -> str:
    value = get_trace_id(request)
    response.headers["X-Trace-Id"] = value
    response.headers["X-Correlation-Id"] = value
    response.headers["X-Request-Id"] = value
    return value


def _tenant_id_value(tenant: Tenant) -> str:
    return str(tenant.id)


class PepRequestIn(BaseModel):
    object_type: str
    object_id: str
    purpose: str
    signer_user_id: str | None = None
    signer_person_id: str | None = None


class PepConfirmIn(BaseModel):
    code: str | None = None


class PepDeclineIn(BaseModel):
    reason: str | None = None


def _pep_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PepNotFound):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(code="PEP_NOT_FOUND", message=str(exc), error_type="pep"),
        )
    if isinstance(exc, PepForbidden):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=api_problem_detail(code="PEP_FORBIDDEN", message=str(exc), error_type="pep"),
        )
    if isinstance(exc, PepConflict):
        # PepApprovalRequired — подкласс PepConflict с отдельным кодом для гейта.
        code = "PEP_APPROVAL_REQUIRED" if isinstance(exc, PepApprovalRequired) else "PEP_CONFLICT"
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_problem_detail(code=code, message=str(exc), error_type="pep"),
        )
    raise AssertionError(f"unexpected pep error: {exc!r}")


def _request_read(row: SignatureRequest) -> dict:
    return {
        "id": row.id,
        "object_type": row.object_type,
        "object_id": row.object_id,
        "purpose": row.purpose,
        "status": row.status,
        "signer_user_id": row.signer_user_id,
        "signer_person_id": row.signer_person_id,
        "signer_name": row.signer_name,
        "content_hash": row.content_hash,
        "signed_at": row.signed_at.isoformat() if row.signed_at else None,
    }


@router.post("/sign/pep/requests", status_code=status.HTTP_201_CREATED)
@audit_operation("create", "pep_signature_request")
async def create_pep_request(
    payload: PepRequestIn,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    x_user_id: str = Header(default="system", alias="X-User-Id"),
) -> dict:
    _correlation_id(request, response)
    svc = PepSigningService(session, _tenant_id_value(tenant))
    try:
        req, code = await svc.create_request(
            object_type=payload.object_type,
            object_id=payload.object_id,
            purpose=payload.purpose,
            requested_by=x_user_id,
            signer_user_id=payload.signer_user_id,
            signer_person_id=payload.signer_person_id,
        )
    except PepNotFound as exc:
        raise _pep_error(exc)
    except PepConflict as exc:
        raise _pep_error(exc)
    await session.commit()
    body = _request_read(req)
    if code is not None:
        body["confirm_code"] = code
    return body


@router.post("/sign/pep/requests/{request_id}/confirm")
@audit_operation("confirm", "pep_signature_request")
async def confirm_pep_request(
    request_id: str,
    payload: PepConfirmIn,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    x_user_id: str = Header(default="system", alias="X-User-Id"),
) -> dict:
    _correlation_id(request, response)
    svc = PepSigningService(session, _tenant_id_value(tenant))
    try:
        req = await svc.confirm(
            request_id,
            code=payload.code,
            acting_user_id=x_user_id,
        )
    except PepForbidden as exc:
        # Состояние не менялось — commit не нужен.
        raise _pep_error(exc)
    except PepConflict as exc:
        # КОНТРАКТ: инкремент попыток сохранён внутри сервиса через flush;
        # обязан COMMIT перед 409, иначе счётчик теряется.
        await session.commit()
        raise _pep_error(exc)
    except PepNotFound as exc:
        raise _pep_error(exc)
    await session.commit()
    return _request_read(req)


@router.post("/sign/pep/requests/{request_id}/decline")
@audit_operation("decline", "pep_signature_request")
async def decline_pep_request(
    request_id: str,
    payload: PepDeclineIn,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    x_user_id: str = Header(default="system", alias="X-User-Id"),
) -> dict:
    _correlation_id(request, response)
    svc = PepSigningService(session, _tenant_id_value(tenant))
    try:
        req = await svc.decline(request_id, reason=payload.reason)
    except PepNotFound as exc:
        raise _pep_error(exc)
    except PepConflict as exc:
        raise _pep_error(exc)
    await session.commit()
    return _request_read(req)


@router.get("/sign/pep/requests")
async def list_pep_requests(
    session: SessionDep,
    tenant: TenantDep,
    _: ReaderAccess,
    object_type: str | None = Query(default=None),
    object_id: str | None = Query(default=None),
    signer_person_id: str | None = Query(default=None),
    purpose: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    stmt = select(SignatureRequest).where(
        SignatureRequest.tenant_id == _tenant_id_value(tenant),
        SignatureRequest.signature_type == "pep",
    )
    if object_type is not None:
        stmt = stmt.where(SignatureRequest.object_type == object_type)
    if object_id is not None:
        stmt = stmt.where(SignatureRequest.object_id == object_id)
    if signer_person_id is not None:
        stmt = stmt.where(SignatureRequest.signer_person_id == signer_person_id)
    if purpose is not None:
        stmt = stmt.where(SignatureRequest.purpose == purpose)
    if status_filter is not None:
        stmt = stmt.where(SignatureRequest.status == status_filter)
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        await session.execute(
            stmt.order_by(
                # Стабильная сортировка: id desc как tie-breaker при равных created_at.
                SignatureRequest.created_at.desc(),
                SignatureRequest.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    return {"items": [_request_read(r) for r in rows], "total": total}


@router.get("/sign/pep/requests/{request_id}/verify")
# GET с побочной записью протокола — осознанный выбор спека (§4);
# audit намеренно нет: read-семантика для клиента.
async def verify_pep_request(
    request_id: str,
    session: SessionDep,
    tenant: TenantDep,
    _: ReaderAccess,
) -> dict:
    svc = PepSigningService(session, _tenant_id_value(tenant))
    try:
        protocol = await svc.verify(request_id)
    except PepNotFound as exc:
        raise _pep_error(exc)
    except PepConflict as exc:
        raise _pep_error(exc)
    await session.commit()
    return protocol


@router.get("/sign/acknowledgements")
async def list_acknowledgements(
    session: SessionDep,
    tenant: TenantDep,
    _: ReaderAccess,
    document_version_id: str | None = Query(default=None),
    person_id: str | None = Query(default=None),
) -> dict:
    stmt = (
        select(SignatureRequest)
        .where(
            SignatureRequest.tenant_id == _tenant_id_value(tenant),
            SignatureRequest.signature_type == "pep",
            SignatureRequest.purpose == "acknowledgement",
        )
        .order_by(SignatureRequest.created_at.desc())
    )
    if document_version_id is not None:
        stmt = stmt.where(
            SignatureRequest.object_type == "document_version",
            SignatureRequest.object_id == document_version_id,
        )
    if person_id is not None:
        stmt = stmt.where(SignatureRequest.signer_person_id == person_id)
    rows = (await session.execute(stmt)).scalars().all()
    return {"items": [_request_read(r) for r in rows]}
