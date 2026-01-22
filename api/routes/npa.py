"""Read-only endpoints for normative legal acts."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_session
from app.core.security import rbac
from app.models.npa import NpaAct
from app.schemas.npa import NpaActListResponse, NpaActRead

router = APIRouter(tags=["npa"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/npa", response_model=NpaActListResponse)
async def list_npa(session: SessionDep, access=Depends(rbac())) -> NpaActListResponse:
    _ = access  # enforce auth
    stmt = select(NpaAct).options(selectinload(NpaAct.clauses)).order_by(NpaAct.code)
    acts = (await session.execute(stmt)).scalars().unique().all()
    return NpaActListResponse(
        items=[NpaActRead.model_validate(act, from_attributes=True) for act in acts]
    )
