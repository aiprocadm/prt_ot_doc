"""CRUD для филиалов (Branch) — master-data уровень между Company и Site (RC-014)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.core.audit_decorator import audit_operation
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import Branch, Company, Tenant
from app.schemas.branch import (
    BranchCreate,
    BranchPage,
    BranchRead,
    BranchUpdate,
)

router = APIRouter(tags=["branches"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_BRANCH_READ_ROLES = ["admin"]
_BRANCH_WRITE_ROLES = ["admin"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ManagerAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_BRANCH_READ_ROLES, action="read branches")),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(
        abac(_tenant_resource_id, required_roles=_BRANCH_WRITE_ROLES, action="manage branches")
    ),
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


async def _get_branch(session: AsyncSession, tenant: Tenant, branch_id: str) -> Branch:
    stmt = select(Branch).where(
        Branch.id == branch_id,
        Branch.tenant_id == tenant.id,
        Branch.deleted_at.is_(None),
    )
    branch = (await session.execute(stmt)).scalar_one_or_none()
    if branch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Branch not found")
    return branch


@router.get("/branches", response_model=BranchPage)
async def list_branches(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
    company_id: str | None = Query(default=None, min_length=1, max_length=36),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> BranchPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = select(Branch).where(Branch.tenant_id == tenant.id, Branch.deleted_at.is_(None))
    if company_id:
        stmt = stmt.where(Branch.company_id == company_id)
    total_stmt = select(func.count()).select_from(stmt.subquery())
    stmt = stmt.order_by(Branch.created_at.desc()).offset(offset).limit(limit)
    items = list((await session.execute(stmt)).scalars().all())
    total = await session.scalar(total_stmt)
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[("total", int(total or 0)), ("limit", limit), ("offset", offset)],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return BranchPage(items=items, total=int(total or 0))


@router.post("/branches", response_model=BranchRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "branch")
async def create_branch(
    payload: BranchCreate, tenant: TenantDep, session: SessionDep, _: EditorAccess
) -> BranchRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    await _get_company(session, tenant, payload.company_id)
    branch = Branch(tenant_id=str(tenant.id), **payload.model_dump())
    session.add(branch)
    await session.flush()
    await session.refresh(branch)
    return BranchRead.model_validate(branch)


@router.get("/branches/{branch_id}", response_model=BranchRead)
async def get_branch(
    branch_id: str, tenant: TenantDep, session: SessionDep, _: ManagerAccess
) -> BranchRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    branch = await _get_branch(session, tenant, branch_id)
    return BranchRead.model_validate(branch)


@router.patch("/branches/{branch_id}", response_model=BranchRead)
@audit_operation("update", "branch")
async def update_branch(
    branch_id: str,
    payload: BranchUpdate,
    tenant: TenantDep,
    session: SessionDep,
    _: EditorAccess,
) -> BranchRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    branch = await _get_branch(session, tenant, branch_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return BranchRead.model_validate(branch)
    for key, value in updates.items():
        setattr(branch, key, value)
    await session.commit()
    await session.refresh(branch)
    return BranchRead.model_validate(branch)


@router.delete("/branches/{branch_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
@audit_operation("delete", "branch")
async def delete_branch(
    branch_id: str, tenant: TenantDep, session: SessionDep, _: EditorAccess
) -> None:
    TenantContextValidator.ensure_tenant_context(tenant)

    branch = await _get_branch(session, tenant, branch_id)
    if branch.deleted_at is None:
        branch.deleted_at = datetime.now(timezone.utc)
    await session.commit()
