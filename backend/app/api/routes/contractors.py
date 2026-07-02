from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.core.feature_flags import is_feature_enabled
from app.core.security import AccessContext, abac
from app.domains.shared import ContingentItemStatus
from app.models.models import Tenant
from app.modules.contractors.documents import document_expiry_status
from app.modules.contractors.models import (
    ComplianceStatus,
    ContractorDocument,
    ContractorDocumentRequirement,
    ContractorEmployee,
    ContractorIncident,
    ContractorRegistry,
)
from app.services.contractor_admission import (
    enforce_contractor_admission,
    evaluate_with_documents,
    load_document_checklist,
)

router = APIRouter(prefix="/contractors", tags=["contractors"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_CONTRACTOR_READ_ROLES = [
    "admin",
    "owner",
    "hse_head",
    "hse_specialist",
    "inspector_contractor",
    "client_admin",
]
_CONTRACTOR_WRITE_ROLES = ["admin", "owner", "hse_head"]

_CONTRACTORS_FEATURE_CODE = "contractors"


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ReaderAccess = Annotated[
    AccessContext,
    Depends(
        abac(_tenant_resource_id, required_roles=_CONTRACTOR_READ_ROLES, action="read contractors")
    ),
]
WriterAccess = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id, required_roles=_CONTRACTOR_WRITE_ROLES, action="manage contractors"
        )
    ),
]


async def require_contractors_feature(tenant: TenantDep, session: SessionDep) -> None:
    if not await is_feature_enabled(session, str(tenant.id), _CONTRACTORS_FEATURE_CODE):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Contractors feature is not enabled for this tenant"
        )


ContractorsFeatureGate = Depends(require_contractors_feature)


class ContractorRegistryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    company_id: str | None = Field(default=None, max_length=36)
    inn: str | None = Field(default=None, max_length=32)
    contact_person: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=64)


class ContractorRegistryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    company_id: str | None = Field(default=None, max_length=36)
    inn: str | None = Field(default=None, max_length=32)
    status: str | None = Field(default=None, max_length=32)
    contact_person: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=64)


class ContractorEmployeeCreate(BaseModel):
    contractor_id: str = Field(min_length=1, max_length=36)
    full_name: str = Field(min_length=1, max_length=255)
    position: str | None = Field(default=None, max_length=255)
    personnel_number: str | None = Field(default=None, max_length=64)
    access_status: ComplianceStatus = ComplianceStatus.PENDING
    training_status: ComplianceStatus = ComplianceStatus.PENDING
    medical_status: ComplianceStatus = ComplianceStatus.PENDING


class ContractorEmployeePatch(BaseModel):
    position: str | None = Field(default=None, max_length=255)
    access_status: ComplianceStatus | None = None
    training_status: ComplianceStatus | None = None
    medical_status: ComplianceStatus | None = None


class ContractorIncidentCreate(BaseModel):
    contractor_id: str = Field(min_length=1, max_length=36)
    employee_id: str | None = Field(default=None, max_length=36)
    incident_type: str = Field(min_length=1, max_length=64)
    severity: str = Field(default="medium", max_length=16)
    status: str = Field(default="open", max_length=32)
    occurred_at: datetime
    description: str | None = None


DocType = Literal[
    "license",
    "insurance",
    "contract",
    "sro",
    "training_cert",
    "medical_cert",
    "access_permit",
    "qualification",
    "other",
]


class ContractorDocumentCreate(BaseModel):
    contractor_id: str = Field(min_length=1, max_length=36)
    employee_id: str | None = Field(default=None, max_length=36)
    doc_type: DocType
    title: str = Field(min_length=1, max_length=255)
    number: str | None = Field(default=None, max_length=128)
    issuing_org: str | None = Field(default=None, max_length=255)
    issued_at: date | None = None
    valid_until: date | None = None
    file_id: str | None = Field(default=None, max_length=36)


Scope = Literal["company", "employee"]


class DocumentRequirementCreate(BaseModel):
    doc_type: DocType
    scope: Scope
    mandatory: bool = True


class ContractorDocumentPatch(BaseModel):
    doc_type: DocType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    number: str | None = Field(default=None, max_length=128)
    issuing_org: str | None = Field(default=None, max_length=255)
    issued_at: date | None = None
    valid_until: date | None = None
    file_id: str | None = Field(default=None, max_length=36)
    status: str | None = Field(default=None, max_length=32)


@router.get("/registry", response_model=None)
async def list_contractors_registry(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: ReaderAccess,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, object] | Response:
    stmt = select(ContractorRegistry).where(
        ContractorRegistry.tenant_id == str(tenant.id),
        ContractorRegistry.deleted_at.is_(None),
    )
    actor = access.to_auth_context()
    access.ensure_abac(action="list contractors")
    contractor_ids = [str(v) for v in access.claims.get("contractor_ids", []) if v]
    if contractor_ids:
        stmt = stmt.where(ContractorRegistry.id.in_(contractor_ids))
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    items = list(
        (
            await session.execute(
                stmt.order_by(ContractorRegistry.created_at.desc()).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[
            ("total", total),
            ("limit", limit),
            ("offset", offset),
            ("roles", "|".join(sorted(actor.roles or []))),
            ("contractors", "|".join(sorted(contractor_ids))),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return {"items": items, "total": total, "roles": actor.roles}


@router.post("/registry", status_code=status.HTTP_201_CREATED)
async def create_contractor_registry(
    payload: ContractorRegistryCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: WriterAccess,
):
    record = ContractorRegistry(tenant_id=str(tenant.id), **payload.model_dump())
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


@router.get("/registry/{contractor_id}")
async def get_contractor_registry(
    contractor_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess
):
    access.ensure_abac(contractor_id=contractor_id, action="read contractors")
    row = (
        await session.execute(
            select(ContractorRegistry).where(
                ContractorRegistry.id == contractor_id,
                ContractorRegistry.tenant_id == str(tenant.id),
                ContractorRegistry.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contractor not found")
    return row


@router.patch("/registry/{contractor_id}")
async def patch_contractor_registry(
    contractor_id: str,
    payload: ContractorRegistryPatch,
    tenant: TenantDep,
    session: SessionDep,
    access: WriterAccess,
):
    access.ensure_abac(contractor_id=contractor_id, action="manage contractors")
    row = (
        await session.execute(
            select(ContractorRegistry).where(
                ContractorRegistry.id == contractor_id,
                ContractorRegistry.tenant_id == str(tenant.id),
                ContractorRegistry.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contractor not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    return row


@router.delete(
    "/registry/{contractor_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def archive_contractor_registry(
    contractor_id: str, tenant: TenantDep, session: SessionDep, access: WriterAccess
):
    access.ensure_abac(contractor_id=contractor_id, action="manage contractors")
    row = (
        await session.execute(
            select(ContractorRegistry).where(
                ContractorRegistry.id == contractor_id,
                ContractorRegistry.tenant_id == str(tenant.id),
                ContractorRegistry.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contractor not found")
    row.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    return None


@router.get("/employees")
async def list_contractor_employees(
    tenant: TenantDep,
    session: SessionDep,
    access: ReaderAccess,
    contractor_id: str | None = Query(default=None),
):
    if contractor_id:
        access.ensure_abac(contractor_id=contractor_id, action="read contractors")
    stmt = select(ContractorEmployee).where(
        ContractorEmployee.tenant_id == str(tenant.id),
        ContractorEmployee.deleted_at.is_(None),
    )
    if contractor_id:
        stmt = stmt.where(ContractorEmployee.contractor_id == contractor_id)
    contractor_ids = [str(v) for v in access.claims.get("contractor_ids", []) if v]
    if contractor_ids:
        stmt = stmt.where(ContractorEmployee.contractor_id.in_(contractor_ids))
    items = list(
        (await session.execute(stmt.order_by(ContractorEmployee.created_at.desc()))).scalars().all()
    )
    return {"items": items, "total": len(items)}


@router.post("/employees", status_code=status.HTTP_201_CREATED)
async def create_contractor_employee(
    payload: ContractorEmployeeCreate, tenant: TenantDep, session: SessionDep, access: WriterAccess
):
    access.ensure_abac(contractor_id=payload.contractor_id, action="manage contractors")
    row = ContractorEmployee(tenant_id=str(tenant.id), **payload.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.patch("/employees/{employee_id}")
async def patch_contractor_employee(
    employee_id: str,
    payload: ContractorEmployeePatch,
    tenant: TenantDep,
    session: SessionDep,
    access: WriterAccess,
):
    row = (
        await session.execute(
            select(ContractorEmployee).where(
                ContractorEmployee.id == employee_id,
                ContractorEmployee.tenant_id == str(tenant.id),
                ContractorEmployee.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    access.ensure_abac(contractor_id=row.contractor_id, action="manage contractors")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/incidents")
async def list_contractor_incidents(
    tenant: TenantDep,
    session: SessionDep,
    access: ReaderAccess,
    contractor_id: str | None = Query(default=None),
):
    if contractor_id:
        access.ensure_abac(contractor_id=contractor_id, action="read contractors")
    stmt = select(ContractorIncident).where(
        ContractorIncident.tenant_id == str(tenant.id),
        ContractorIncident.deleted_at.is_(None),
    )
    if contractor_id:
        stmt = stmt.where(ContractorIncident.contractor_id == contractor_id)
    contractor_ids = [str(v) for v in access.claims.get("contractor_ids", []) if v]
    if contractor_ids:
        stmt = stmt.where(ContractorIncident.contractor_id.in_(contractor_ids))
    items = list(
        (await session.execute(stmt.order_by(ContractorIncident.occurred_at.desc())))
        .scalars()
        .all()
    )
    return {"items": items, "total": len(items)}


@router.post("/incidents", status_code=status.HTTP_201_CREATED)
async def create_contractor_incident(
    payload: ContractorIncidentCreate, tenant: TenantDep, session: SessionDep, access: WriterAccess
):
    access.ensure_abac(contractor_id=payload.contractor_id, action="manage contractors")
    row = ContractorIncident(tenant_id=str(tenant.id), **payload.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/compliance-summary")
async def contractor_compliance_summary(
    tenant: TenantDep,
    session: SessionDep,
    access: ReaderAccess,
    contractor_id: str | None = Query(default=None),
):
    if contractor_id:
        access.ensure_abac(contractor_id=contractor_id, action="read contractors")

    stmt = select(ContractorEmployee).where(
        ContractorEmployee.tenant_id == str(tenant.id),
        ContractorEmployee.deleted_at.is_(None),
    )
    if contractor_id:
        stmt = stmt.where(ContractorEmployee.contractor_id == contractor_id)
    contractor_ids = [str(v) for v in access.claims.get("contractor_ids", []) if v]
    if contractor_ids:
        stmt = stmt.where(ContractorEmployee.contractor_id.in_(contractor_ids))

    employees = list((await session.execute(stmt)).scalars().all())
    return {
        "contractor_id": contractor_id,
        "employees_total": len(employees),
        "admission": _status_totals([item.access_status.value for item in employees]),
        "training": _status_totals([item.training_status.value for item in employees]),
        "medical": _status_totals([item.medical_status.value for item in employees]),
    }


def _status_totals(values: list[str]) -> dict[str, int]:
    result = {status.value: 0 for status in ComplianceStatus}
    for value in values:
        if value not in result:
            continue
        result[value] += 1
    return result


# ---------------------------------------------------------------------------
# Admission helpers
# ---------------------------------------------------------------------------


async def _fetch_employee(
    session: AsyncSession, tenant: Tenant, employee_id: str
) -> ContractorEmployee:
    """Return the in-tenant, non-deleted ContractorEmployee or raise 404."""
    row = (
        await session.execute(
            select(ContractorEmployee).where(
                ContractorEmployee.id == employee_id,
                ContractorEmployee.tenant_id == str(tenant.id),
                ContractorEmployee.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    return row


def _verdict_body(verdict) -> dict:
    return {
        "employee_id": verdict.employee_id,
        "status": verdict.status.value,
        "violations": verdict.violations,
        "warnings": verdict.warnings,
    }


# ---------------------------------------------------------------------------
# Admission endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/employees/{employee_id}/readiness",
    dependencies=[ContractorsFeatureGate],
)
async def get_employee_readiness(
    employee_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ReaderAccess,
) -> dict:
    """Advisory readiness check for a contractor employee (no side-effects)."""
    row = await _fetch_employee(session, tenant, employee_id)
    access.ensure_abac(contractor_id=row.contractor_id, action="read contractors")
    verdict = (await evaluate_with_documents(session, employees=[row]))[0]
    return _verdict_body(verdict)


@router.get(
    "/employees/{employee_id}/document-checklist",
    dependencies=[ContractorsFeatureGate],
)
async def get_employee_document_checklist(
    employee_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ReaderAccess,
) -> dict:
    """Per-requirement document collection status for a contractor employee (advisory)."""
    row = await _fetch_employee(session, tenant, employee_id)
    access.ensure_abac(contractor_id=row.contractor_id, action="read contractors")
    items = await load_document_checklist(session, employee=row)
    return {"employee_id": employee_id, "items": items}


@router.post(
    "/employees/{employee_id}/admit",
    dependencies=[ContractorsFeatureGate],
)
async def admit_contractor_employee(
    employee_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: WriterAccess,
) -> dict:
    """Admission gate for a contractor employee.

    Returns 200 with the verdict body when the employee is cleared. A non-blocked
    employee may still carry ``status: "warning"`` (e.g. a deadline due soon) with
    a 200 — only ``BLOCKED`` employees are rejected with 409. A missing/cross-tenant
    id yields 404.
    """
    row = await _fetch_employee(session, tenant, employee_id)
    access.ensure_abac(contractor_id=row.contractor_id, action="manage contractors")
    try:
        await enforce_contractor_admission(
            session,
            tenant_scope=(str(tenant.id),),
            employee_ids=[employee_id],
        )
    except ValueError as exc:
        payload = exc.args[0] if exc.args else {}
        code = payload.get("code") if isinstance(payload, dict) else None
        if code == "employees_not_found":
            # Race: row vanished between the 404 pre-check and enforce. 404 is the
            # honest answer — never report a missing employee as "requirements_not_met".
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found") from exc
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "requirements_not_met",
                "error_code": "requirements_not_met",
                "message": "Contractor employee is not cleared for admission",
                "type": "contractors",
                "details": payload.get("details", []) if isinstance(payload, dict) else [],
            },
        ) from exc
    # enforce is read-only, so ``row`` (loaded above) is still fresh; re-evaluate
    # (including documents) to surface the non-blocked verdict in the success body.
    return _verdict_body((await evaluate_with_documents(session, employees=[row]))[0])


# ---------------------------------------------------------------------------
# Document registry
# ---------------------------------------------------------------------------


def _document_body(doc: ContractorDocument, today: date | None = None) -> dict:
    if today is None:
        today = datetime.now(timezone.utc).date()
    return {
        "id": doc.id,
        "contractor_id": doc.contractor_id,
        "employee_id": doc.employee_id,
        "doc_type": doc.doc_type,
        "title": doc.title,
        "number": doc.number,
        "issuing_org": doc.issuing_org,
        "issued_at": doc.issued_at.isoformat() if doc.issued_at else None,
        "valid_until": doc.valid_until.isoformat() if doc.valid_until else None,
        "file_id": doc.file_id,
        "status": doc.status,
        "expiry_status": document_expiry_status(doc.valid_until, today).value,
    }


async def _fetch_document(
    session: AsyncSession, tenant: Tenant, document_id: str
) -> ContractorDocument:
    """Return the in-tenant, non-deleted ContractorDocument or raise 404."""
    row = (
        await session.execute(
            select(ContractorDocument).where(
                ContractorDocument.id == document_id,
                ContractorDocument.tenant_id == str(tenant.id),
                ContractorDocument.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return row


async def _validate_employee_belongs(
    session: AsyncSession, tenant: Tenant, contractor_id: str, employee_id: str
) -> None:
    """422 if employee_id does not belong to contractor_id within the tenant."""
    emp = (
        await session.execute(
            select(ContractorEmployee).where(
                ContractorEmployee.id == employee_id,
                ContractorEmployee.tenant_id == str(tenant.id),
                ContractorEmployee.contractor_id == contractor_id,
                ContractorEmployee.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if emp is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "employee_id does not belong to contractor_id",
        )


@router.get("/documents", dependencies=[ContractorsFeatureGate])
async def list_contractor_documents(
    tenant: TenantDep,
    session: SessionDep,
    access: ReaderAccess,
    contractor_id: str | None = Query(default=None),
    employee_id: str | None = Query(default=None),
    doc_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> dict:
    if contractor_id:
        access.ensure_abac(contractor_id=contractor_id, action="read contractors")
    stmt = select(ContractorDocument).where(
        ContractorDocument.tenant_id == str(tenant.id),
        ContractorDocument.deleted_at.is_(None),
    )
    if contractor_id:
        stmt = stmt.where(ContractorDocument.contractor_id == contractor_id)
    if employee_id:
        stmt = stmt.where(ContractorDocument.employee_id == employee_id)
    if doc_type:
        stmt = stmt.where(ContractorDocument.doc_type == doc_type)
    if status_filter:
        stmt = stmt.where(ContractorDocument.status == status_filter)
    contractor_ids = [str(v) for v in access.claims.get("contractor_ids", []) if v]
    if contractor_ids:
        stmt = stmt.where(ContractorDocument.contractor_id.in_(contractor_ids))
    items = list(
        (await session.execute(stmt.order_by(ContractorDocument.created_at.desc()))).scalars().all()
    )
    today = datetime.now(timezone.utc).date()
    return {"items": [_document_body(d, today) for d in items], "total": len(items)}


@router.post(
    "/documents", status_code=status.HTTP_201_CREATED, dependencies=[ContractorsFeatureGate]
)
async def create_contractor_document(
    payload: ContractorDocumentCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: WriterAccess,
) -> dict:
    access.ensure_abac(contractor_id=payload.contractor_id, action="manage contractors")
    if payload.employee_id:
        await _validate_employee_belongs(
            session, tenant, payload.contractor_id, payload.employee_id
        )
    row = ContractorDocument(tenant_id=str(tenant.id), **payload.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _document_body(row)


@router.get("/documents/expiring", dependencies=[ContractorsFeatureGate])
async def list_expiring_contractor_documents(
    tenant: TenantDep,
    session: SessionDep,
    access: ReaderAccess,
    contractor_id: str | None = Query(default=None),
) -> dict:
    """Advisory: documents whose expiry_status is DUE_SOON or OVERDUE."""
    if contractor_id:
        access.ensure_abac(contractor_id=contractor_id, action="read contractors")
    stmt = select(ContractorDocument).where(
        ContractorDocument.tenant_id == str(tenant.id),
        ContractorDocument.deleted_at.is_(None),
        ContractorDocument.valid_until.is_not(None),
    )
    if contractor_id:
        stmt = stmt.where(ContractorDocument.contractor_id == contractor_id)
    contractor_ids = [str(v) for v in access.claims.get("contractor_ids", []) if v]
    if contractor_ids:
        stmt = stmt.where(ContractorDocument.contractor_id.in_(contractor_ids))
    today = datetime.now(timezone.utc).date()
    flagged = [
        _document_body(d, today)
        for d in (await session.execute(stmt)).scalars().all()
        if document_expiry_status(d.valid_until, today)
        in (
            ContingentItemStatus.DUE_SOON,
            ContingentItemStatus.OVERDUE,
        )
    ]
    return {"items": flagged, "total": len(flagged)}


@router.get("/documents/{document_id}", dependencies=[ContractorsFeatureGate])
async def get_contractor_document(
    document_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess
) -> dict:
    row = await _fetch_document(session, tenant, document_id)
    access.ensure_abac(contractor_id=row.contractor_id, action="read contractors")
    return _document_body(row)


@router.patch("/documents/{document_id}", dependencies=[ContractorsFeatureGate])
async def patch_contractor_document(
    document_id: str,
    payload: ContractorDocumentPatch,
    tenant: TenantDep,
    session: SessionDep,
    access: WriterAccess,
) -> dict:
    row = await _fetch_document(session, tenant, document_id)
    access.ensure_abac(contractor_id=row.contractor_id, action="manage contractors")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    return _document_body(row)


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[ContractorsFeatureGate],
)
async def archive_contractor_document(
    document_id: str, tenant: TenantDep, session: SessionDep, access: WriterAccess
):
    row = await _fetch_document(session, tenant, document_id)
    access.ensure_abac(contractor_id=row.contractor_id, action="manage contractors")
    row.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    return None


# ---------------------------------------------------------------------------
# Document-requirement policy (tenant-level)
# ---------------------------------------------------------------------------


def _requirement_body(req: ContractorDocumentRequirement) -> dict:
    return {
        "id": req.id,
        "doc_type": req.doc_type,
        "scope": req.scope,
        "mandatory": req.mandatory,
    }


@router.get("/document-requirements", dependencies=[ContractorsFeatureGate])
async def list_document_requirements(
    tenant: TenantDep, session: SessionDep, access: ReaderAccess
) -> dict:
    rows = list(
        (
            await session.execute(
                select(ContractorDocumentRequirement)
                .where(
                    ContractorDocumentRequirement.tenant_id == str(tenant.id),
                    ContractorDocumentRequirement.deleted_at.is_(None),
                )
                .order_by(ContractorDocumentRequirement.doc_type)
            )
        )
        .scalars()
        .all()
    )
    return {"items": [_requirement_body(r) for r in rows], "total": len(rows)}


@router.post(
    "/document-requirements",
    status_code=status.HTTP_201_CREATED,
    dependencies=[ContractorsFeatureGate],
)
async def create_document_requirement(
    payload: DocumentRequirementCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: WriterAccess,
) -> dict:
    existing = (
        await session.execute(
            select(ContractorDocumentRequirement).where(
                ContractorDocumentRequirement.tenant_id == str(tenant.id),
                ContractorDocumentRequirement.doc_type == payload.doc_type,
                ContractorDocumentRequirement.scope == payload.scope,
                ContractorDocumentRequirement.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "requirement_exists",
                "message": "Requirement already exists for this doc_type/scope",
            },
        )
    row = ContractorDocumentRequirement(tenant_id=str(tenant.id), **payload.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _requirement_body(row)


@router.delete(
    "/document-requirements/{requirement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[ContractorsFeatureGate],
)
async def delete_document_requirement(
    requirement_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: WriterAccess,
):
    row = (
        await session.execute(
            select(ContractorDocumentRequirement).where(
                ContractorDocumentRequirement.id == requirement_id,
                ContractorDocumentRequirement.tenant_id == str(tenant.id),
                ContractorDocumentRequirement.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Requirement not found")
    row.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    return None
