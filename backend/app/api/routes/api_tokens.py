from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, abac
from app.models.models import ApiToken, Tenant
from app.schemas.api_tokens import ApiTokenCreateRequest, ApiTokenCreateResponse, ApiTokenRead
from app.services.api_tokens import ApiTokenService
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api-tokens", tags=["api-tokens"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


OwnerAdminAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=["owner", "admin"], action="read")),
]


@router.get("", response_model=list[ApiTokenRead])
async def list_api_tokens(
    session: SessionDep,
    access: OwnerAdminAccess,
    tenant: Tenant = Depends(get_tenant_record),
) -> list[ApiTokenRead]:
    _ = access
    rows = (
        (
            await session.execute(
                select(ApiToken)
                .where(ApiToken.tenant_id == tenant.id, ApiToken.deleted_at.is_(None))
                .order_by(ApiToken.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        ApiTokenRead(
            id=item.id,
            name=item.name,
            scopes=list(item.scopes_json or []),
            created_at=item.created_at,
            last_used_at=item.last_used_at,
            expires_at=item.expires_at,
            is_revoked=bool(item.is_revoked),
        )
        for item in rows
    ]


@router.post("", response_model=ApiTokenCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_token(
    payload: ApiTokenCreateRequest,
    session: SessionDep,
    access: OwnerAdminAccess,
    tenant: Tenant = Depends(get_tenant_record),
) -> ApiTokenCreateResponse:
    raw, token = ApiTokenService.issue_token(
        tenant_id=tenant.id,
        name=payload.name,
        scopes=payload.scopes,
        created_by_user_id=getattr(access.user, "id", None) if access else None,
        expires_at=payload.expires_at,
    )
    session.add(token)
    await session.commit()
    await session.refresh(token)
    return ApiTokenCreateResponse(
        id=token.id,
        name=token.name,
        scopes=list(token.scopes_json or []),
        token=raw,
        expires_at=token.expires_at,
        created_at=token.created_at,
    )


@router.delete("/{token_id}", status_code=status.HTTP_200_OK)
async def revoke_api_token(
    token_id: str,
    session: SessionDep,
    access: OwnerAdminAccess,
    tenant: Tenant = Depends(get_tenant_record),
) -> dict[str, str]:
    _ = access
    token = await session.get(ApiToken, token_id)
    if token is None or token.tenant_id != tenant.id or token.deleted_at is not None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "TOKEN_NOT_FOUND", "message": "API token not found"},
        )
    token.is_revoked = True
    token.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    return {"status": "ok"}
