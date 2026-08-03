"""OPS-73 срез-3: платформенный обзор устареваний API.

Разд. 73.2 «Мониторинг использования»: админу управляющего арендатора видно,
какие поверхности объявлены устаревшими и КТО из арендаторов ещё ходит в них
живьём (2xx) — прямой ответ на вопрос «можно ли уже отключать». Гейт — тот же,
что у управления парком арендаторов (данные межарендаторские, обычному
tenant-админу их видеть нельзя).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.routes.platform_tenants import _require_managing_admin
from app.core.api_deprecation import API_DEPRECATIONS
from app.models.api_deprecation_usage import ApiDeprecationUsage
from app.models.tenanting import Tenant

router = APIRouter()
_optional_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class DeprecationEntryRead(BaseModel):
    path_prefix: str
    deprecated_since: str
    sunset: str
    successor: str
    docs_url: str


class DeprecationUsageRead(BaseModel):
    tenant_slug: str
    path_prefix: str
    first_seen_at: datetime
    last_seen_at: datetime
    hits_2xx: int
    last_notified_at: datetime | None


class DeprecationOverview(BaseModel):
    registry: list[DeprecationEntryRead]
    usage: list[DeprecationUsageRead]


@router.get("", response_model=DeprecationOverview)
async def deprecation_overview(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> DeprecationOverview:
    _require_managing_admin(credentials, tenant)
    rows = (
        (
            await session.execute(
                select(ApiDeprecationUsage).order_by(ApiDeprecationUsage.last_seen_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return DeprecationOverview(
        registry=[
            DeprecationEntryRead(
                path_prefix=e.path_prefix,
                deprecated_since=e.deprecated_since.isoformat(),
                sunset=e.sunset.isoformat(),
                successor=e.successor,
                docs_url=e.docs_url,
            )
            for e in API_DEPRECATIONS
        ],
        usage=[DeprecationUsageRead.model_validate(r, from_attributes=True) for r in rows],
    )
