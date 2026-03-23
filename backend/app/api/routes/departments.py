from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, abac
from app.core.audit_decorator import audit_operation
from app.models.finance import Department
from app.models.models import Company, Tenant
from app.schemas.department import DepartmentCreate, DepartmentPage, DepartmentRead, DepartmentUpdate

router = APIRouter(tags=["departments"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_department_roles = ["admin", "owner", "hr", "line_manager"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


DepartmentAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_department_roles, action="manage departments")),
]


async def _get_company(session: AsyncSession, tenant: Tenant, company_id: str) -> Company:
    stmt = select(Company).where(
        Company.id == company_id,
        Company.tenant_id == tenant.id,
        Company.deleted_at.is_(None),
    )
    company = (await session.execute(stmt)).scalar_one_or_none()
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    return company


async def _get_department(session: AsyncSession, tenant: Tenant, department_id: str) -> Department:
    stmt = select(Department).where(
        Department.id == department_id,
        Department.tenant_id == tenant.id,
        Department.deleted_at.is_(None),
    )
    department = (await session.execute(stmt)).scalar_one_or_none()
    if department is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")
    return department


@router.get("/departments", response_model=DepartmentPage)
async def list_departments(
    tenant: TenantDep,
    session: SessionDep,
    _: DepartmentAccess,
    company_id: str | None = Query(default=None, min_length=1, max_length=36),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> DepartmentPage:
    stmt = select(Department).where(
        Department.tenant_id == tenant.id,
        Department.deleted_at.is_(None),
    )
    if company_id:
        stmt = stmt.where(Department.company_id == company_id)
    total_stmt = select(func.count()).select_from(stmt.subquery())
    stmt = stmt.order_by(Department.created_at.desc()).offset(offset).limit(limit)
    items = list((await session.execute(stmt)).scalars().all())
    total = await session.scalar(total_stmt)
    return DepartmentPage(items=items, total=int(total or 0))


@router.post("/departments", response_model=DepartmentRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "department")
async def create_department(
    payload: DepartmentCreate,
    tenant: TenantDep,
    session: SessionDep,
    _: DepartmentAccess,
) -> DepartmentRead:
    await _get_company(session, tenant, payload.company_id)
    department = Department(tenant_id=str(tenant.id), **payload.model_dump())
    session.add(department)
    await session.commit()
    await session.refresh(department)
    return DepartmentRead.model_validate(department)


@router.get("/departments/{department_id}", response_model=DepartmentRead)
async def get_department(
    department_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: DepartmentAccess,
) -> DepartmentRead:
    department = await _get_department(session, tenant, department_id)
    return DepartmentRead.model_validate(department)


@router.patch("/departments/{department_id}", response_model=DepartmentRead)
@audit_operation("update", "department")
async def update_department(
    department_id: str,
    payload: DepartmentUpdate,
    tenant: TenantDep,
    session: SessionDep,
    _: DepartmentAccess,
) -> DepartmentRead:
    department = await _get_department(session, tenant, department_id)
    updates = payload.model_dump(exclude_unset=True)
    if "company_id" in updates:
        await _get_company(session, tenant, str(updates["company_id"]))
    for key, value in updates.items():
        setattr(department, key, value)
    await session.commit()
    await session.refresh(department)
    return DepartmentRead.model_validate(department)


@router.delete(
    "/departments/{department_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
@audit_operation("delete", "department")
async def delete_department(
    department_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: DepartmentAccess,
) -> None:
    department = await _get_department(session, tenant, department_id)
    if department.deleted_at is None:
        department.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
