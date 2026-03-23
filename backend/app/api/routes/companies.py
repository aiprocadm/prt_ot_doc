"""Company CRUD endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.rbac_abac import actor_from_claims, policy_forbidden
from app.core.security import AccessContext, abac
from app.models.models import Company, Tenant
from app.repository import create_company, list_companies
from app.schemas.company import CompanyCreate, CompanyPage, CompanyRead, CompanyUpdate
from app.services.audit import AuditService, field_level_diff

router = APIRouter(prefix="/companies", tags=["companies"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


_defense_roles = ["admin", "owner"]
_COMPANY_READ_ROLES = ["admin", "owner"]
_COMPANY_WRITE_ROLES = ["admin", "owner"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ManagerAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_COMPANY_READ_ROLES, action="read companies")),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_COMPANY_WRITE_ROLES, action="manage companies")),
]


def _company_unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "company_validation_error", "message": message},
    )


async def _get_company_or_404(
    session: AsyncSession, tenant: Tenant, company_id: str
) -> Company:
    stmt = select(Company).where(
        Company.id == company_id,
        Company.tenant_id == tenant.id,
        Company.deleted_at.is_(None),
    )
    company = (await session.execute(stmt)).scalar_one_or_none()
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    return company


def _clean_string(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _clean_list(values: list[str] | None) -> list[str]:
    if not values:
        return []
    cleaned: list[str] = []
    for item in values:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized:
            cleaned.append(normalized)
    return cleaned


def _apply_company_updates(company: Company, payload: CompanyUpdate) -> None:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return

    str_fields = [
        "name",
        "inn",
        "kpp",
        "ogrn",
        "activity_type",
        "legal_address",
        "actual_address",
        "director",
        "bank_name",
        "bank_bik",
        "bank_account",
        "logo_file_id",
        "stamp_file_id",
        "preferred_header_preset_code",
    ]
    list_fields = ["phone_numbers", "work_types", "hazardous_factors", "okved_codes"]

    for field in str_fields:
        if field in data:
            cleaned = _clean_string(data[field])
            if field == "name" and cleaned is None:
                raise _company_unprocessable("name cannot be empty")
            setattr(company, field, cleaned)

    for field in list_fields:
        if field in data:
            setattr(company, field, _clean_list(data[field]))

    if "email" in data:
        company.email = _clean_string(data["email"]) or None
    if "contact_email" in data:
        company.contact_email = _clean_string(data["contact_email"]) or None
    if "contact_person" in data:
        company.contact_person = _clean_string(data["contact_person"]) or None
    if "contact_phone" in data:
        company.contact_phone = _clean_string(data["contact_phone"]) or None
    if "is_hazardous_production_facility" in data:
        company.is_hazardous_production_facility = bool(
            data["is_hazardous_production_facility"]
        )
    if "has_dangerous_objects" in data:
        company.has_dangerous_objects = bool(data["has_dangerous_objects"])
    if "branding_payload" in data and data["branding_payload"] is not None:
        company.branding_payload = data["branding_payload"]


@router.get("", response_model=CompanyPage)
async def list_companies_endpoint(
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> CompanyPage:
    companies, total = await list_companies(
        session,
        tenant.id,
        limit=limit,
        offset=offset,
        claims=dict(access.claims),
        roles=access.to_auth_context().roles,
    )
    return CompanyPage(items=companies, total=total)


@router.post("", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
async def create_company_endpoint(
    request: Request,
    payload: CompanyCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> CompanyRead:
    try:
        company = await create_company(session, tenant.id, payload)
        await AuditService(session).log_event(
            tenant_id=str(tenant.id),
            action="create",
            object_type="Company",
            object_id=company.id,
            user_id=access.user.id,
            ip=request.client.host if request.client else "unknown",
            request_id=getattr(request.state, "trace_id", None),
            user_agent=request.headers.get("user-agent"),
            changed_fields={"fields": {"id": {"before": None, "after": company.id}}},
            details={"entity": "Company"},
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Company with this name already exists"
        ) from exc
    return CompanyRead.model_validate(company)


@router.get("/{company_id}", response_model=CompanyRead)
async def get_company_endpoint(
    request: Request,
    company_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
) -> CompanyRead:
    company = await _get_company_or_404(session, tenant, company_id)
    actor = actor_from_claims(dict(access.claims), access.to_auth_context().roles)
    if actor.company_ids and company.id not in actor.company_ids:
        await AuditService(session).log_event(
            tenant_id=str(tenant.id),
            action="access_deny",
            object_type="companies",
            object_id=company.id,
            user_id=access.user.id,
            ip=request.client.host if request.client else "unknown",
            request_id=getattr(request.state, "trace_id", None),
            user_agent=request.headers.get("user-agent"),
            details={
                "type": "policy",
                "reason": "Company scope mismatch for read companies",
            },
        )
        await session.commit()
        raise policy_forbidden("Company scope mismatch for read companies")
    return CompanyRead.model_validate(company)


@router.patch("/{company_id}", response_model=CompanyRead)
async def update_company_endpoint(
    request: Request,
    company_id: str,
    payload: CompanyUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> CompanyRead:
    company = await _get_company_or_404(session, tenant, company_id)
    before = CompanyRead.model_validate(company).model_dump()
    _apply_company_updates(company, payload)
    try:
        after = CompanyRead.model_validate(company).model_dump()
        await AuditService(session).log_event(
            tenant_id=str(tenant.id),
            action="update",
            object_type="Company",
            object_id=company.id,
            user_id=access.user.id,
            ip=request.client.host if request.client else "unknown",
            request_id=getattr(request.state, "trace_id", None),
            user_agent=request.headers.get("user-agent"),
            changed_fields=field_level_diff(before, after),
            details={"entity": "Company"},
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Company with this name already exists") from exc
    await session.refresh(company)
    return CompanyRead.model_validate(company)


@router.delete(
    "/{company_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def archive_company_endpoint(
    request: Request,
    company_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> None:
    company = await _get_company_or_404(session, tenant, company_id)
    if company.deleted_at is None:
        before = {"deleted_at": None}
        company.deleted_at = datetime.now(timezone.utc)
        await AuditService(session).log_event(
            tenant_id=str(tenant.id),
            action="delete",
            object_type="Company",
            object_id=company.id,
            user_id=access.user.id,
            ip=request.client.host if request.client else "unknown",
            request_id=getattr(request.state, "trace_id", None),
            user_agent=request.headers.get("user-agent"),
            changed_fields=field_level_diff(before, {"deleted_at": company.deleted_at}),
            details={"entity": "Company", "soft": True},
        )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
