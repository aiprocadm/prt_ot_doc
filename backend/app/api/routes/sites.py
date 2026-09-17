from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_correlation_id, get_session, get_tenant_record
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.core.audit_decorator import audit_operation
from app.core.screen_access import screen_roles
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.db.session import rearm_session_tenant_context
from app.domains.sites.overview import collect_site_overview
from app.models.models import (
    Branch,
    Company,
    Site,
    Tenant,
    Workplace,
    WorkplaceHazardLink,
)
from app.models.risk import RiskHazard
from app.schemas.site import (
    SiteCreate,
    SiteDisciplineRead,
    SiteFactsRead,
    SiteNotCountedRead,
    SiteOverviewRead,
    SitePage,
    SitePermitFactsRead,
    SiteRead,
    SiteUpdate,
    WorkplaceCreate,
    WorkplacePage,
    WorkplaceRead,
    WorkplaceUpdate,
)

router = APIRouter(tags=["sites"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_manager_roles = ["admin"]
_SITE_WRITE_ROLES = list(screen_roles("branch.manage"))
# Кто может писать — обязан мочь читать (backend/tests/test_*_access_parity.py):
# читатели = карта прав экрана ∪ писатели. Срез-217 дал чтению круг из карты, а
# запись оставил на прежнем списке — и сотрудник мог создать, но не увидеть.
_SITE_READ_ROLES = sorted(set(screen_roles("reference.view")) | set(_SITE_WRITE_ROLES))


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ManagerAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_SITE_READ_ROLES, action="read sites")),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_SITE_WRITE_ROLES, action="manage sites")),
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


async def _ensure_branch_link(
    session: AsyncSession, tenant: Tenant, branch_id: str, company_id: str
) -> None:
    """RC-014: site.branch_id — app-level ссылка (нет DB FK), целостность держит API."""
    stmt = select(Branch).where(
        Branch.id == branch_id,
        Branch.tenant_id == tenant.id,
        Branch.deleted_at.is_(None),
    )
    branch = (await session.execute(stmt)).scalar_one_or_none()
    if branch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Branch not found")
    if branch.company_id != company_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Branch belongs to a different company")


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


async def _get_workplace(session: AsyncSession, tenant: Tenant, workplace_id: str) -> Workplace:
    stmt = select(Workplace).where(
        Workplace.id == workplace_id,
        Workplace.tenant_id == tenant.id,
        Workplace.deleted_at.is_(None),
    )
    workplace = (await session.execute(stmt)).scalar_one_or_none()
    if workplace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workplace not found")
    return workplace


async def _ensure_hazards(session: AsyncSession, tenant_id: str, hazard_ids: list[str]) -> None:
    if not hazard_ids:
        return
    stmt = select(RiskHazard.id).where(
        RiskHazard.tenant_id == tenant_id, RiskHazard.id.in_(hazard_ids)
    )
    rows = (await session.execute(stmt)).scalars().all()
    missing = set(hazard_ids) - set(rows)
    if missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Hazards not found: {', '.join(missing)}")


@router.get("/sites", response_model=SitePage)
async def list_sites(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
    company_id: str | None = Query(default=None, min_length=1, max_length=36),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> SitePage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = select(Site).where(Site.tenant_id == tenant.id, Site.deleted_at.is_(None))
    if company_id:
        stmt = stmt.where(Site.company_id == company_id)
    total_stmt = select(func.count()).select_from(stmt.subquery())
    stmt = stmt.order_by(Site.created_at.desc()).offset(offset).limit(limit)
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
    return SitePage(items=items, total=int(total or 0))


@router.post("/sites", response_model=SiteRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "site")
async def create_site(
    payload: SiteCreate, tenant: TenantDep, session: SessionDep, _: EditorAccess
) -> SiteRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    await _get_company(session, tenant, payload.company_id)
    if payload.branch_id:
        await _ensure_branch_link(session, tenant, payload.branch_id, payload.company_id)
    site = Site(tenant_id=str(tenant.id), **payload.model_dump())
    session.add(site)
    await session.flush()
    await session.refresh(site)
    return SiteRead.model_validate(site)


@router.get("/sites/{site_id}", response_model=SiteRead)
async def get_site(
    site_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
    correlation_id: str = Depends(get_correlation_id),
) -> SiteRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    site = await _get_site(session, tenant, site_id)
    return SiteRead.model_validate(site)


@router.get("/sites/{site_id}/overview", response_model=SiteOverviewRead)
async def get_site_overview(
    site_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
) -> SiteOverviewRead:
    """Карточка площадки 360° (BIZ-54-57 срез-3, Доп. №1 разд. 57.1).

    **Круг читателей тот же, что у самой площадки** (``ManagerAccess``).
    Карточка агрегирует медосмотры, СИЗ и обучение людей площадки — это
    персональные данные, и расширять круг читателей мимоходом, «раз уж экран
    новый», нельзя: в срезе-1 ручка без ролевого правила показала бы сотруднику
    медосмотры всего арендатора. Понадобится специалисту без прав админа —
    это отдельное решение о доступе к ПДн, а не побочный эффект новой ручки.

    **Читатель, привязанный к компании, видит только её площадки.** Тот же урок
    среза-1: в арендаторе-аутсорсере админ одного клиента иначе прочитал бы
    сводку по людям другого. Отвечаем 404, а не 403: 403 подтвердил бы, что
    такая площадка существует.
    """

    TenantContextValidator.ensure_tenant_context(tenant)

    site = await _get_site(session, tenant, site_id)
    scoped_company = getattr(access, "company_id", None)
    if scoped_company and str(site.company_id) != str(scoped_company):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    overview = await collect_site_overview(session, tenant_id=str(tenant.id), site=site)
    return SiteOverviewRead(
        site_id=overview.site_id,
        name=overview.name,
        company_id=overview.company_id,
        address=overview.address,
        hazard_class=overview.hazard_class,
        is_hazardous_production_facility=overview.is_hazardous_production_facility,
        opo_register_number=overview.opo_register_number,
        overall=overview.overall.value,
        disciplines=[
            SiteDisciplineRead(
                discipline=row.discipline.value,
                title=row.title,
                light=row.light.value,
                reason=row.reason,
                required=row.counts.required,
                missing=row.counts.missing,
                lapsed=row.counts.lapsed,
                expiring=row.counts.expiring,
            )
            for row in overview.disciplines
        ],
        facts=SiteFactsRead(
            workplaces=overview.facts.workplaces,
            people=overview.facts.people,
            people_without_workplace=overview.facts.people_without_workplace,
            permits=SitePermitFactsRead(
                total=overview.facts.permits.total,
                by_discipline={
                    discipline.value: count
                    for discipline, count in overview.facts.permits.by_discipline.items()
                },
                without_discipline=overview.facts.permits.without_discipline,
                without_discipline_titles=list(overview.facts.permits.without_discipline_titles),
                without_discipline_reason=overview.facts.permits.without_discipline_reason,
            ),
        ),
        not_counted=[
            SiteNotCountedRead(title=title, reason=reason) for title, reason in overview.not_counted
        ],
    )


@router.patch("/sites/{site_id}", response_model=SiteRead)
@audit_operation("update", "site")
async def update_site(
    site_id: str,
    payload: SiteUpdate,
    tenant: TenantDep,
    session: SessionDep,
    _: EditorAccess,
) -> SiteRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    site = await _get_site(session, tenant, site_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return SiteRead.model_validate(site)
    if "company_id" in updates:
        await _get_company(session, tenant, str(updates["company_id"]))
    if updates.get("branch_id"):
        target_company = str(updates.get("company_id") or site.company_id)
        await _ensure_branch_link(session, tenant, str(updates["branch_id"]), target_company)
    for key, value in updates.items():
        setattr(site, key, value)
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(site)
    return SiteRead.model_validate(site)


@router.delete("/sites/{site_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
@audit_operation("delete", "site")
async def delete_site(
    site_id: str, tenant: TenantDep, session: SessionDep, _: EditorAccess
) -> None:
    TenantContextValidator.ensure_tenant_context(tenant)

    site = await _get_site(session, tenant, site_id)
    if site.deleted_at is None:
        site.deleted_at = datetime.now(timezone.utc)
    await session.commit()


@router.get("/workplaces", response_model=WorkplacePage)
async def list_workplaces(
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
    company_id: str | None = Query(default=None, min_length=1, max_length=36),
    site_id: str | None = Query(default=None, min_length=1, max_length=36),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> WorkplacePage:
    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = select(Workplace).where(
        Workplace.tenant_id == tenant.id,
        Workplace.deleted_at.is_(None),
    )
    if company_id:
        stmt = stmt.where(Workplace.company_id == company_id)
    if site_id:
        stmt = stmt.where(Workplace.site_id == site_id)
    total_stmt = select(func.count()).select_from(stmt.subquery())
    stmt = stmt.order_by(Workplace.created_at.desc()).offset(offset).limit(limit)
    items = list((await session.execute(stmt)).scalars().all())
    total = await session.scalar(total_stmt)
    return WorkplacePage(items=items, total=int(total or 0))


async def _replace_workplace_hazards(
    session: AsyncSession,
    tenant: Tenant,
    workplace: Workplace,
    hazard_ids: list[str],
    document_ids: list[str],
) -> None:
    await session.execute(
        delete(WorkplaceHazardLink).where(WorkplaceHazardLink.workplace_id == workplace.id)
    )
    await _ensure_hazards(session, str(tenant.id), hazard_ids)
    document_map = {
        hid: document_ids[idx] if idx < len(document_ids) else None
        for idx, hid in enumerate(hazard_ids)
    }
    links = [
        WorkplaceHazardLink(
            tenant_id=workplace.tenant_id,
            workplace_id=workplace.id,
            hazard_id=hazard_id,
            document_file_id=document_map.get(hazard_id),
        )
        for hazard_id in hazard_ids
    ]
    if links:
        session.add_all(links)


@router.post("/workplaces", response_model=WorkplaceRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "workplace")
async def create_workplace(
    payload: WorkplaceCreate, tenant: TenantDep, session: SessionDep, _: EditorAccess
) -> WorkplaceRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    await _get_company(session, tenant, payload.company_id)
    if payload.site_id:
        await _get_site(session, tenant, payload.site_id)
    hazard_ids = payload.hazard_ids or []
    document_ids = payload.document_file_ids or []
    workplace = Workplace(
        tenant_id=str(tenant.id),
        company_id=payload.company_id,
        site_id=payload.site_id,
        name=payload.name,
        description=payload.description,
        location=payload.location,
        working_conditions_class=payload.working_conditions_class,
    )
    session.add(workplace)
    await session.flush()
    if hazard_ids:
        await _replace_workplace_hazards(session, tenant, workplace, hazard_ids, document_ids)
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(workplace)
    return WorkplaceRead.model_validate(workplace)


@router.get("/workplaces/{workplace_id}", response_model=WorkplaceRead)
async def get_workplace(
    workplace_id: str, tenant: TenantDep, session: SessionDep, _: ManagerAccess
) -> WorkplaceRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    workplace = await _get_workplace(session, tenant, workplace_id)
    return WorkplaceRead.model_validate(workplace)


@router.patch("/workplaces/{workplace_id}", response_model=WorkplaceRead)
@audit_operation("update", "workplace")
async def update_workplace(
    workplace_id: str,
    payload: WorkplaceUpdate,
    tenant: TenantDep,
    session: SessionDep,
    _: EditorAccess,
) -> WorkplaceRead:
    workplace = await _get_workplace(session, tenant, workplace_id)
    data = payload.model_dump(exclude_unset=True)
    if "company_id" in data:
        await _get_company(session, tenant, str(data["company_id"]))
    if "site_id" in data and data["site_id"]:
        await _get_site(session, tenant, str(data["site_id"]))
    for field in [
        "company_id",
        "site_id",
        "name",
        "description",
        "location",
        "working_conditions_class",
    ]:
        if field in data:
            setattr(workplace, field, data[field])
    hazard_ids = data.get("hazard_ids")
    document_ids = data.get("document_file_ids") or []
    if hazard_ids is not None:
        await _replace_workplace_hazards(session, tenant, workplace, hazard_ids, document_ids)
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(workplace)
    return WorkplaceRead.model_validate(workplace)


@router.delete(
    "/workplaces/{workplace_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
@audit_operation("delete", "workplace")
async def delete_workplace(
    workplace_id: str, tenant: TenantDep, session: SessionDep, _: EditorAccess
) -> None:
    TenantContextValidator.ensure_tenant_context(tenant)

    workplace = await _get_workplace(session, tenant, workplace_id)
    if workplace.deleted_at is None:
        workplace.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
    await session.execute(
        delete(WorkplaceHazardLink).where(WorkplaceHazardLink.workplace_id == workplace.id)
    )
    await session.commit()
