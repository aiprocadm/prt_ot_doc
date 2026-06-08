from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

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
from app.models.models import Tenant
from app.modules.contractors.models import (
    ComplianceStatus,
    ContractorEmployee,
    ContractorIncident,
    ContractorRegistry,
)
from app.services.contractor_admission import (
    enforce_contractor_admission,
    evaluate_contractor_admission,
)

router = APIRouter(prefix="/contractors", tags=["contractors"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_CONTRACTOR_READ_ROLES = ["admin", "owner", "hse_head", "hse_specialist", "inspector_contractor", "client_admin"]
_CONTRACTOR_WRITE_ROLES = ["admin", "owner", "hse_head"]

_CONTRACTORS_FEATURE_CODE = "contractors"


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ReaderAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_CONTRACTOR_READ_ROLES, action="read contractors")),
]
WriterAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_CONTRACTOR_WRITE_ROLES, action="manage contractors")),
]


async def require_contractors_feature(tenant: TenantDep, session: SessionDep) -> None:
    if not await is_feature_enabled(session, str(tenant.id), _CONTRACTORS_FEATURE_CODE):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contractors feature is not enabled for this tenant")


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
    items = list((await session.execute(stmt.order_by(ContractorRegistry.created_at.desc()).offset(offset).limit(limit))).scalars().all())
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
async def get_contractor_registry(contractor_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess):
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
async def patch_contractor_registry(contractor_id: str, payload: ContractorRegistryPatch, tenant: TenantDep, session: SessionDep, access: WriterAccess):
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


@router.delete("/registry/{contractor_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def archive_contractor_registry(contractor_id: str, tenant: TenantDep, session: SessionDep, access: WriterAccess):
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
    items = list((await session.execute(stmt.order_by(ContractorEmployee.created_at.desc()))).scalars().all())
    return {"items": items, "total": len(items)}


@router.post("/employees", status_code=status.HTTP_201_CREATED)
async def create_contractor_employee(payload: ContractorEmployeeCreate, tenant: TenantDep, session: SessionDep, access: WriterAccess):
    access.ensure_abac(contractor_id=payload.contractor_id, action="manage contractors")
    row = ContractorEmployee(tenant_id=str(tenant.id), **payload.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.patch("/employees/{employee_id}")
async def patch_contractor_employee(employee_id: str, payload: ContractorEmployeePatch, tenant: TenantDep, session: SessionDep, access: WriterAccess):
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
    items = list((await session.execute(stmt.order_by(ContractorIncident.occurred_at.desc()))).scalars().all())
    return {"items": items, "total": len(items)}


@router.post("/incidents", status_code=status.HTTP_201_CREATED)
async def create_contractor_incident(payload: ContractorIncidentCreate, tenant: TenantDep, session: SessionDep, access: WriterAccess):
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
    verdict = evaluate_contractor_admission(employees=[row])[0]
    return _verdict_body(verdict)


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
    """Admission gate — raises 409 if the employee is BLOCKED."""
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
    return _verdict_body(evaluate_contractor_admission(employees=[row])[0])
