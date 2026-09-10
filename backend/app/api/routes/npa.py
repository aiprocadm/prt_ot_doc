"""Реестр нормативных актов: чтение для всех, ведение — владельцу платформы.

Реестр общий (``NpaAct`` — SharedModel, без tenant_id): один и тот же приказ
Минтруда действует на всех арендаторов. Поэтому заводить акты и редакции
может только владелец платформы — тот же гейт, что у кабинета арендаторов
(``_require_managing_admin``). До среза-141 писать в реестр было некому вовсе:
``GET /npa`` отдавал пустой список всегда, а экран НПА предлагал «добавить
или импортировать» акты, не имея ни одной ручки для этого.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_session, get_tenant_record
from app.api.routes.platform_tenants import _require_managing_admin
from app.core.audit_decorator import audit_operation
from app.core.security import abac, rbac
from app.core.tenant_validation import TenantContextValidator
from app.domains.npa.impact import NpaImpactService
from app.models.models import Tenant
from app.models.npa import NpaAct, NpaClause, NpaRevision
from app.schemas.npa import (
    NpaActCreate,
    NpaActListResponse,
    NpaActRead,
    NpaRevisionCreate,
    NpaRevisionRead,
)

router = APIRouter(tags=["npa"])
_optional_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# NPA reads (`GET /npa*`) stay authn-only — normative acts are reference data. Creating
# update tasks from an act's impact writes tenant-wide task rows -> DOC_WRITE (mirrors
# the export/report write set: admin/owner/ot_specialist).
_IMPACT_WRITE_ROLES = ["admin", "owner", "ot_specialist"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


def _can_manage(credentials: HTTPAuthorizationCredentials | None, tenant: Tenant) -> bool:
    """Тот же вопрос, что задаёт гейт записи, — но ответом «да/нет», без отказа.

    Список читают все, а кнопку «Добавить акт» должен видеть только тот, кому
    ручка записи ответит 201. Считать это на витрине по роли нельзя: право
    зависит ещё и от того, управляющий ли арендатор, — а это знает только
    бэкенд (``settings.managing_tenant_slug``).
    """

    try:
        _require_managing_admin(credentials, tenant)
    except HTTPException:
        return False
    return True


@router.get("/npa", response_model=NpaActListResponse)
async def list_npa(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    access=Depends(rbac()),
) -> NpaActListResponse:
    _ = access  # enforce auth
    stmt = select(NpaAct).options(selectinload(NpaAct.clauses)).order_by(NpaAct.code)
    acts = (await session.execute(stmt)).scalars().unique().all()
    return NpaActListResponse(
        items=[NpaActRead.model_validate(act, from_attributes=True) for act in acts],
        can_manage=_can_manage(credentials, tenant),
    )


@router.post("/npa", response_model=NpaActRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "npa_act")
async def create_npa_act(
    payload: NpaActCreate,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> NpaActRead:
    """Срез-141: единственная точка входа в общий реестр актов."""

    _require_managing_admin(credentials, tenant)
    duplicate = await session.scalar(select(NpaAct.id).where(NpaAct.code == payload.code))
    if duplicate is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Акт с таким кодом уже есть в реестре")
    act = NpaAct(
        code=payload.code,
        title=payload.title,
        edition=payload.edition,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
    )
    act.clauses.extend(NpaClause(code=clause.code, text=clause.text) for clause in payload.clauses)
    session.add(act)
    try:
        await session.commit()
    except IntegrityError as exc:
        # Гонка двух одинаковых заявок: проверка выше её не видит, уникальный
        # индекс — видит. Ответ тот же, что и без гонки.
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Акт с таким кодом уже есть в реестре"
        ) from exc
    await session.refresh(act, attribute_names=["clauses"])
    return NpaActRead.model_validate(act, from_attributes=True)


@router.post(
    "/npa/{act_id}/revisions",
    response_model=NpaRevisionRead,
    status_code=status.HTTP_201_CREATED,
)
@audit_operation("create", "npa_revision")
async def create_npa_revision(
    act_id: str,
    payload: NpaRevisionCreate,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> NpaRevisionRead:
    """Срез-141: новая редакция акта — её и читает оценка влияния."""

    _require_managing_admin(credentials, tenant)
    act = await session.get(NpaAct, act_id)
    if act is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "NPA act not found")
    duplicate = await session.scalar(
        select(NpaRevision.id).where(
            NpaRevision.act_id == act_id, NpaRevision.revision_code == payload.revision_code
        )
    )
    if duplicate is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Редакция с таким кодом у акта уже есть")
    revision = NpaRevision(
        act_id=act.id,
        revision_code=payload.revision_code,
        title=payload.title,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        change_summary=payload.change_summary,
    )
    session.add(revision)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Редакция с таким кодом у акта уже есть"
        ) from exc
    await session.refresh(revision)
    return NpaRevisionRead.model_validate(revision, from_attributes=True)


@router.get("/npa/{act_id}")
async def get_npa_detail(
    act_id: str,
    session: SessionDep,
    revision_id: str | None = Query(default=None),
    tenant: Tenant = Depends(get_tenant_record),
    access=Depends(rbac()),
) -> dict:
    TenantContextValidator.ensure_tenant_context(tenant)

    _ = access
    payload = await NpaImpactService(session, str(tenant.id)).detail(
        act_id, revision_id=revision_id
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="NPA act not found")
    return payload


@router.post("/npa/{act_id}/impact/tasks")
@audit_operation("create_tasks", "npa_impact")
async def create_npa_update_tasks(
    act_id: str,
    session: SessionDep,
    revision_id: str | None = Query(default=None),
    tenant: Tenant = Depends(get_tenant_record),
    access=Depends(
        abac(
            _tenant_resource_id,
            required_roles=_IMPACT_WRITE_ROLES,
            action="create npa update tasks",
        )
    ),
) -> dict:
    TenantContextValidator.ensure_tenant_context(tenant)

    tasks = await NpaImpactService(session, str(tenant.id)).create_update_tasks(
        act_id, getattr(access.user, "id", None), revision_id=revision_id
    )
    await session.commit()
    return {
        "created": len(tasks),
        "items": [{"id": item.id, "title": item.title} for item in tasks],
    }
