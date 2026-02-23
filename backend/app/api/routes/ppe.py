"""Endpoints for PPE catalogue and issuance."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, abac
from app.domains.ppe import issue_ppe_item, list_expiring_issues
from app.models.models import PPEIssue, PPEIssueStatus, PPEItem, Tenant
from app.schemas.ppe import (
    PPEIssueCreate,
    PPEIssuePage,
    PPEIssueRead,
    PPEIssueUpdate,
    PPEItemCreate,
    PPEItemPage,
    PPEItemRead,
    PPEItemUpdate,
)
from app.services.events import EventType
from app.services.outbox import OutboxService

router = APIRouter(prefix="/ppe", tags=["ppe"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ManagerAccess = Annotated[
    AccessContext, Depends(abac(_tenant_resource_id, required_roles=["admin"]))
]


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
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PPEItemPage:
    stmt = (
        select(PPEItem)
        .where(PPEItem.tenant_id == tenant.id, PPEItem.deleted_at.is_(None))
        .order_by(PPEItem.name.asc())
        .limit(limit)
        .offset(offset)
    )
    items = (await session.execute(stmt)).scalars().all()
    total = (
        await session.execute(
            select(func.count()).where(
                PPEItem.tenant_id == tenant.id, PPEItem.deleted_at.is_(None)
            )
        )
    ).scalar_one()
    return PPEItemPage(items=[_item_schema(item) for item in items], total=total)


@router.post("/items", response_model=PPEItemRead, status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: PPEItemCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
) -> PPEItemRead:
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
async def get_item(item_id: str, tenant: TenantDep, session: SessionDep, access: ManagerAccess) -> PPEItemRead:
    item = await _get_item(session, tenant, item_id)
    return _item_schema(item)


@router.patch("/items/{item_id}", response_model=PPEItemRead)
async def update_item(
    item_id: str,
    payload: PPEItemUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
) -> PPEItemRead:
    item = await _get_item(session, tenant, item_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    await session.flush()
    await session.refresh(item)
    return _item_schema(item)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_item(
    item_id: str, tenant: TenantDep, session: SessionDep, access: ManagerAccess
) -> None:
    item = await _get_item(session, tenant, item_id)
    if item.deleted_at is None:
        item.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/issues", response_model=PPEIssuePage)
async def list_issues(
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    person_id: str | None = None,
    active_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PPEIssuePage:
    stmt = select(PPEIssue).where(PPEIssue.tenant_id == tenant.id, PPEIssue.deleted_at.is_(None))
    if person_id:
        stmt = stmt.where(PPEIssue.person_id == person_id)
    if active_only:
        stmt = stmt.where(PPEIssue.status == PPEIssueStatus.ISSUED)
    stmt = stmt.order_by(PPEIssue.issued_at.desc()).limit(limit).offset(offset)
    issues = (await session.execute(stmt)).scalars().all()
    count_stmt = select(func.count()).where(
        PPEIssue.tenant_id == tenant.id,
        PPEIssue.deleted_at.is_(None),
    )
    if person_id:
        count_stmt = count_stmt.where(PPEIssue.person_id == person_id)
    if active_only:
        count_stmt = count_stmt.where(PPEIssue.status == PPEIssueStatus.ISSUED)
    total = (await session.execute(count_stmt)).scalar_one()
    return PPEIssuePage(items=[_issue_schema(item) for item in issues], total=total)


@router.get("/issues/expiring", response_model=PPEIssuePage)
async def expiring_issues(
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    within_days: int = Query(30, ge=1, le=365),
) -> PPEIssuePage:
    issues = await list_expiring_issues(session, tenant_id=tenant.id, within_days=within_days)
    return PPEIssuePage(items=[_issue_schema(item) for item in issues], total=len(issues))


@router.post("/issues", response_model=PPEIssueRead, status_code=status.HTTP_201_CREATED)
async def create_issue(
    payload: PPEIssueCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
) -> PPEIssueRead:
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
async def get_issue(issue_id: str, tenant: TenantDep, session: SessionDep, access: ManagerAccess) -> PPEIssueRead:
    issue = await _get_issue(session, tenant, issue_id)
    return _issue_schema(issue)


@router.patch("/issues/{issue_id}", response_model=PPEIssueRead)
async def update_issue(
    issue_id: str,
    payload: PPEIssueUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
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
