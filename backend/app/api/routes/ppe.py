"""Endpoints for PPE catalogue and issuance."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_correlation_id, get_session, get_tenant_record
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.feature_flags import is_feature_enabled
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.domains.ppe import issue_ppe_item, list_expiring_issues
from app.models.ppe_registry import PPEIssue, PPEIssueStatus, PPEItem, PPEStockBatch
from app.models.tenanting import Tenant
from app.schemas.ppe import (
    PPEIssueCreate,
    PPEIssuePage,
    PPEIssueRead,
    PPEIssueUpdate,
    PPEItemCreate,
    PPEItemPage,
    PPEItemRead,
    PPEItemUpdate,
    PPEStockBatchCreate,
    PPEStockBatchPage,
    PPEStockBatchRead,
    PPEStockBatchUpdate,
    PPEStockLevelPage,
    PPEStockLevelRead,
)
from app.services.events import EventType
from app.services.outbox import OutboxService

router = APIRouter(prefix="/ppe", tags=["ppe"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


_PPE_READ_ROLES = ["admin"]
_PPE_WRITE_ROLES = ["admin"]


ManagerAccess = Annotated[
    AccessContext, Depends(abac(_tenant_resource_id, required_roles=_PPE_READ_ROLES))
]
EditorAccess = Annotated[
    AccessContext, Depends(abac(_tenant_resource_id, required_roles=_PPE_WRITE_ROLES))
]


def _ppe_bad_request(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=api_problem_detail(code="PPE_VALIDATION_ERROR", message=message, error_type="ppe"),
    )


async def _get_item(session: AsyncSession, tenant: Tenant, item_id: str) -> PPEItem:
    stmt = select(PPEItem).where(
        PPEItem.id == item_id,
        PPEItem.tenant_id == tenant.id,
        PPEItem.deleted_at.is_(None),
    )
    item = (await session.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PPE item not found")
    return item


async def _get_issue(session: AsyncSession, tenant: Tenant, issue_id: str) -> PPEIssue:
    stmt = select(PPEIssue).where(
        PPEIssue.id == issue_id,
        PPEIssue.tenant_id == tenant.id,
        PPEIssue.deleted_at.is_(None),
    )
    issue = (await session.execute(stmt)).scalar_one_or_none()
    if issue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PPE issue not found")
    return issue


def _item_schema(item: PPEItem) -> PPEItemRead:
    return PPEItemRead.model_validate(item)


def _issue_schema(issue: PPEIssue) -> PPEIssueRead:
    return PPEIssueRead.model_validate(issue)


@router.get("/items", response_model=PPEItemPage)
async def list_items(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PPEItemPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = (
        select(PPEItem)
        .where(PPEItem.tenant_id == tenant.id, PPEItem.deleted_at.is_(None))
        .order_by(PPEItem.name.asc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await session.execute(stmt)).scalars().all())
    total = (
        await session.execute(
            select(func.count()).where(
                PPEItem.tenant_id == tenant.id, PPEItem.deleted_at.is_(None)
            )
        )
    ).scalar_one()
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
    return PPEItemPage(items=[_item_schema(item) for item in items], total=total)


@router.post("/items", response_model=PPEItemRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "ppe_item")
async def create_item(
    payload: PPEItemCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPEItemRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    item = PPEItem(
        tenant_id=tenant.id,
        name=payload.name,
        code=payload.code,
        category=payload.category,
        description=payload.description,
        default_wear_days=payload.default_wear_days,
        metadata_json=payload.metadata_json,
    )
    session.add(item)
    await session.flush()
    await session.refresh(item)
    return _item_schema(item)


@router.get("/items/{item_id}", response_model=PPEItemRead)
async def get_item(item_id: str, tenant: TenantDep, session: SessionDep, access: ManagerAccess,
    correlation_id: str = Depends(get_correlation_id)) -> PPEItemRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    item = await _get_item(session, tenant, item_id)
    return _item_schema(item)


@router.patch("/items/{item_id}", response_model=PPEItemRead)
@audit_operation("update", "ppe_item")
async def update_item(
    item_id: str,
    payload: PPEItemUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPEItemRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    item = await _get_item(session, tenant, item_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    await session.flush()
    await session.refresh(item)
    return _item_schema(item)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
@audit_operation("delete", "ppe_item")
async def delete_item(
    item_id: str, tenant: TenantDep, session: SessionDep, access: EditorAccess
) -> None:
    TenantContextValidator.ensure_tenant_context(tenant)

    item = await _get_item(session, tenant, item_id)
    if item.deleted_at is None:
        item.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/issues", response_model=PPEIssuePage)
async def list_issues(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    person_id: str | None = None,
    active_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PPEIssuePage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = select(PPEIssue).where(PPEIssue.tenant_id == tenant.id, PPEIssue.deleted_at.is_(None))
    if person_id:
        stmt = stmt.where(PPEIssue.person_id == person_id)
    if active_only:
        stmt = stmt.where(PPEIssue.status == PPEIssueStatus.ISSUED)
    stmt = stmt.order_by(PPEIssue.issued_at.desc()).limit(limit).offset(offset)
    issues = list((await session.execute(stmt)).scalars().all())
    count_stmt = select(func.count()).where(
        PPEIssue.tenant_id == tenant.id,
        PPEIssue.deleted_at.is_(None),
    )
    if person_id:
        count_stmt = count_stmt.where(PPEIssue.person_id == person_id)
    if active_only:
        count_stmt = count_stmt.where(PPEIssue.status == PPEIssueStatus.ISSUED)
    total = (await session.execute(count_stmt)).scalar_one()
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=issues,
        scalars=[
            ("total", int(total or 0)),
            ("limit", limit),
            ("offset", offset),
            ("person", person_id or ""),
            ("active_only", "1" if active_only else "0"),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return PPEIssuePage(items=[_issue_schema(item) for item in issues], total=total)


@router.get("/issues/expiring", response_model=PPEIssuePage)
async def expiring_issues(
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    within_days: int = Query(30, ge=1, le=365),
) -> PPEIssuePage:
    TenantContextValidator.ensure_tenant_context(tenant)

    issues = await list_expiring_issues(session, tenant_id=tenant.id, within_days=within_days)
    return PPEIssuePage(items=[_issue_schema(item) for item in issues], total=len(issues))


@router.post("/issues", response_model=PPEIssueRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "ppe_issue")
async def create_issue(
    payload: PPEIssueCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPEIssueRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    try:
        issue = await issue_ppe_item(
            session,
            tenant_id=tenant.id,
            person_id=payload.person_id,
            item_id=payload.item_id,
            quantity=payload.quantity,
            issued_at=payload.issued_at,
            wear_days=payload.wear_days,
            expires_at=payload.expires_at,
        )
    except ValueError as exc:
        raise _ppe_bad_request(str(exc)) from exc
    outbox = OutboxService(session)
    await outbox.enqueue(
        tenant_id=str(tenant.id),
        event_type=EventType.PPE_ISSUED.value,
        payload={
            "tenant_id": str(tenant.id),
            "actor_id": access.user.id if access else None,
            "occurred_at": issue.issued_at,
            "ppe_issue_id": issue.id,
            "person_id": issue.person_id,
            "item_id": issue.item_id,
            "quantity": issue.quantity,
            "issued_at": issue.issued_at,
            "expires_at": issue.expires_at,
            "status": issue.status.value,
        },
    )
    return _issue_schema(issue)


@router.get("/issues/{issue_id}", response_model=PPEIssueRead)
async def get_issue(
    issue_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    correlation_id: str = Depends(get_correlation_id),
) -> PPEIssueRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    issue = await _get_issue(session, tenant, issue_id)
    return _issue_schema(issue)


@router.patch("/issues/{issue_id}", response_model=PPEIssueRead)
@audit_operation("update", "ppe_issue")
async def update_issue(
    issue_id: str,
    payload: PPEIssueUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPEIssueRead:
    issue = await _get_issue(session, tenant, issue_id)
    previous_status = issue.status
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(issue, field, value)
    if issue.status == PPEIssueStatus.RETURNED and issue.returned_at is None:
        issue.returned_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(issue)
    if previous_status != PPEIssueStatus.RETURNED and issue.status == PPEIssueStatus.RETURNED:
        outbox = OutboxService(session)
        await outbox.enqueue(
            tenant_id=str(tenant.id),
            event_type=EventType.PPE_RETURNED.value,
            payload={
                "tenant_id": str(tenant.id),
                "actor_id": access.user.id if access else None,
                "occurred_at": issue.returned_at or datetime.now(timezone.utc),
                "ppe_issue_id": issue.id,
                "person_id": issue.person_id,
                "item_id": issue.item_id,
                "quantity": issue.quantity,
                "returned_at": issue.returned_at or datetime.now(timezone.utc),
                "status": issue.status.value,
            },
        )
    return _issue_schema(issue)


# --- PPE warehouse (stock) pilot feature gate (W-A / TZ-3.2-V11-01) ---------
# The /ppe/stock/* endpoints sit behind the per-tenant ``warehouse`` pilot flag
# (docs/FEATURE_FLAGS.md). Default-on: a tenant only loses access by storing
# FeatureEnablement(on=False) for Feature(code="warehouse"). Disabled tenants
# get 404 (feature stays invisible) rather than 403.
_WAREHOUSE_FEATURE_CODE = "warehouse"


async def require_warehouse_feature(tenant: TenantDep, session: SessionDep) -> None:
    if not await is_feature_enabled(session, str(tenant.id), _WAREHOUSE_FEATURE_CODE):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "PPE warehouse feature is not enabled for this tenant",
        )


WarehouseFeatureGate = Depends(require_warehouse_feature)


async def _get_batch(session: AsyncSession, tenant: Tenant, batch_id: str) -> PPEStockBatch:
    stmt = select(PPEStockBatch).where(
        PPEStockBatch.id == batch_id,
        PPEStockBatch.tenant_id == tenant.id,
        PPEStockBatch.deleted_at.is_(None),
    )
    batch = (await session.execute(stmt)).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PPE stock batch not found")
    return batch


@router.get(
    "/stock/batches",
    response_model=PPEStockBatchPage,
    dependencies=[WarehouseFeatureGate],
)
async def list_stock_batches(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,    item_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PPEStockBatchPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = select(PPEStockBatch).where(
        PPEStockBatch.tenant_id == tenant.id, PPEStockBatch.deleted_at.is_(None)
    )
    if item_id:
        stmt = stmt.where(PPEStockBatch.item_id == item_id)
    stmt = stmt.order_by(PPEStockBatch.batch_no.asc()).limit(limit).offset(offset)
    batches = list((await session.execute(stmt)).scalars().all())

    count_stmt = select(func.count()).where(
        PPEStockBatch.tenant_id == tenant.id, PPEStockBatch.deleted_at.is_(None)
    )
    if item_id:
        count_stmt = count_stmt.where(PPEStockBatch.item_id == item_id)
    total = (await session.execute(count_stmt)).scalar_one()

    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=batches,
        scalars=[
            ("total", int(total or 0)),
            ("limit", limit),
            ("offset", offset),
            ("item", item_id or ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return PPEStockBatchPage(
        items=[PPEStockBatchRead.model_validate(b) for b in batches], total=total
    )


@router.post(
    "/stock/batches",
    response_model=PPEStockBatchRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[WarehouseFeatureGate],
)
@audit_operation("create", "ppe_stock_batch")
async def create_stock_batch(
    payload: PPEStockBatchCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,) -> PPEStockBatchRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    await _get_item(session, tenant, payload.item_id)

    batch = PPEStockBatch(
        tenant_id=tenant.id,
        item_id=payload.item_id,
        batch_no=payload.batch_no,
        quantity=payload.quantity,
        received_at=payload.received_at,
        certificate_no=payload.certificate_no,
        certificate_expires_at=payload.certificate_expires_at,
        location=payload.location,
    )
    session.add(batch)
    await session.flush()
    await session.refresh(batch)
    return PPEStockBatchRead.model_validate(batch)


@router.get(
    "/stock/batches/{batch_id}",
    response_model=PPEStockBatchRead,
    dependencies=[WarehouseFeatureGate],
)
async def get_stock_batch(
    batch_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,) -> PPEStockBatchRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    batch = await _get_batch(session, tenant, batch_id)
    return PPEStockBatchRead.model_validate(batch)


@router.patch(
    "/stock/batches/{batch_id}",
    response_model=PPEStockBatchRead,
    dependencies=[WarehouseFeatureGate],
)
@audit_operation("update", "ppe_stock_batch")
async def update_stock_batch(
    batch_id: str,
    payload: PPEStockBatchUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,) -> PPEStockBatchRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    batch = await _get_batch(session, tenant, batch_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(batch, field, value)
    await session.flush()
    await session.refresh(batch)
    return PPEStockBatchRead.model_validate(batch)


@router.get(
    "/stock/levels",
    response_model=PPEStockLevelPage,
    dependencies=[WarehouseFeatureGate],
)
async def list_stock_levels(
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,) -> PPEStockLevelPage:
    TenantContextValidator.ensure_tenant_context(tenant)

    agg_stmt = (
        select(
            PPEStockBatch.item_id,
            func.coalesce(func.sum(PPEStockBatch.quantity), 0),
            func.count(PPEStockBatch.id),
            func.min(PPEStockBatch.certificate_expires_at),
        )
        .where(
            PPEStockBatch.tenant_id == tenant.id,
            PPEStockBatch.deleted_at.is_(None),
        )
        .group_by(PPEStockBatch.item_id)
    )
    rows = (await session.execute(agg_stmt)).all()

    names: dict[str, str] = {}
    item_ids = [row[0] for row in rows]
    if item_ids:
        name_rows = (
            await session.execute(
                select(PPEItem.id, PPEItem.name).where(PPEItem.id.in_(item_ids))
            )
        ).all()
        names = {item_id: name for item_id, name in name_rows}

    levels = [
        PPEStockLevelRead(
            item_id=row[0],
            item_name=names.get(row[0], ""),
            total_quantity=int(row[1] or 0),
            batch_count=int(row[2] or 0),
            nearest_certificate_expiry=row[3],
        )
        for row in rows
    ]
    return PPEStockLevelPage(items=levels, total=len(levels))
