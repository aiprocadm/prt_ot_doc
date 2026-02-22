from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, abac
from app.models.finance import Contract, ContractStatus, Department
from app.models.models import Company, Site, Tenant
from app.schemas.contract import ContractCreate, ContractPage, ContractRead, ContractUpdate

router = APIRouter(tags=["contracts"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_finance_roles = ["admin", "owner", "accountant"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


FinanceAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_finance_roles, action="manage contracts")),
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


async def _get_department(
    session: AsyncSession, tenant: Tenant, department_id: str
) -> Department:
    stmt = select(Department).where(
        Department.id == department_id,
        Department.tenant_id == tenant.id,
        Department.deleted_at.is_(None),
    )
    department = (await session.execute(stmt)).scalar_one_or_none()
    if department is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")
    return department


async def _get_site(session: AsyncSession, tenant: Tenant, site_id: str) -> Site:
    stmt = select(Site).where(
        Site.id == site_id,
        Site.tenant_id == tenant.id,
        Site.deleted_at.is_(None),
    )
    site = (await session.execute(stmt)).scalar_one_or_none()
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    return site


async def _get_contract(session: AsyncSession, tenant: Tenant, contract_id: str) -> Contract:
    stmt = select(Contract).where(
        Contract.id == contract_id,
        Contract.tenant_id == tenant.id,
        Contract.deleted_at.is_(None),
    )
    contract = (await session.execute(stmt)).scalar_one_or_none()
    if contract is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contract not found")
    return contract


@router.get("/contracts", response_model=ContractPage)
async def list_contracts(
    tenant: TenantDep,
    session: SessionDep,
    _: FinanceAccess,
    company_id: str | None = Query(default=None, min_length=1, max_length=36),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ContractPage:
    stmt = select(Contract).where(
        Contract.tenant_id == tenant.id,
        Contract.deleted_at.is_(None),
    )
    if company_id:
        stmt = stmt.where(Contract.company_id == company_id)
    total_stmt = select(func.count()).select_from(stmt.subquery())
    stmt = stmt.order_by(Contract.created_at.desc()).offset(offset).limit(limit)
    items = list((await session.execute(stmt)).scalars().all())
    total = await session.scalar(total_stmt)
    return ContractPage(items=items, total=int(total or 0))


@router.post("/contracts", response_model=ContractRead, status_code=status.HTTP_201_CREATED)
async def create_contract(
    payload: ContractCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: FinanceAccess,
) -> ContractRead:
    company = await _get_company(session, tenant, payload.company_id)
    department_id = payload.department_id
    if department_id:
        department = await _get_department(session, tenant, department_id)
        if department.company_id != company.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Department does not belong to company")
    site_id = payload.site_id
    site_company_id = None
    if site_id:
        site = await _get_site(session, tenant, site_id)
        site_company_id = site.company_id
    access.ensure_site_access(site_id, site_company_id, action="assign contract site")

    if payload.status:
        try:
            status_value = ContractStatus(str(payload.status).lower())
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported contract status") from exc
    else:
        status_value = ContractStatus.DRAFT
    contract = Contract(
        tenant_id=str(tenant.id),
        company_id=company.id,
        department_id=payload.department_id,
        site_id=payload.site_id,
        title=payload.title,
        counterparty_name=payload.counterparty_name,
        contract_number=payload.contract_number,
        status=status_value,
        signed_at=payload.signed_at,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        total_amount=payload.total_amount,
        currency=payload.currency or "RUB",
    )
    session.add(contract)
    await session.commit()
    await session.refresh(contract)
    return ContractRead.model_validate(contract)


@router.get("/contracts/{contract_id}", response_model=ContractRead)
async def get_contract(
    contract_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: FinanceAccess,
) -> ContractRead:
    contract = await _get_contract(session, tenant, contract_id)
    return ContractRead.model_validate(contract)


@router.patch("/contracts/{contract_id}", response_model=ContractRead)
async def update_contract(
    contract_id: str,
    payload: ContractUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: FinanceAccess,
) -> ContractRead:
    contract = await _get_contract(session, tenant, contract_id)
    updates = payload.model_dump(exclude_unset=True)
    if "company_id" in updates:
        company = await _get_company(session, tenant, str(updates["company_id"]))
        contract.company_id = company.id
    if "department_id" in updates and updates["department_id"]:
        department = await _get_department(session, tenant, str(updates["department_id"]))
        if department.company_id != contract.company_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Department does not belong to company")
    if "site_id" in updates and updates["site_id"]:
        site = await _get_site(session, tenant, str(updates["site_id"]))
        access.ensure_site_access(site.id, site.company_id, action="update contract site")
    if "status" in updates and updates["status"]:
        try:
            updates["status"] = ContractStatus(str(updates["status"]).lower())
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported contract status") from exc

    for key, value in updates.items():
        setattr(contract, key, value)
    await session.commit()
    await session.refresh(contract)
    return ContractRead.model_validate(contract)


@router.delete(
    "/contracts/{contract_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_contract(
    contract_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: FinanceAccess,
) -> None:
    contract = await _get_contract(session, tenant, contract_id)
    if contract.deleted_at is None:
        contract.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    return None
