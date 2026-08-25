"""Контур экологии, собственные ручки (Доп. №1 разд. 55.1, срез-1).

Реестр объектов негативного воздействия на окружающую среду: постановка на
государственный учёт, категория I–IV, актуализация сведений. До этого среза по
экологии не было ни одной сущности — дисциплина существовала словарной строкой,
а весь контент сводился к комплекту документов, где всё вводится руками.

Гейт модуля — роутерный (разд. 61.3): на каждом роуте по построению,
аутентификация РАНЬШЕ гейта (иначе без токена вернулся бы 404 вместо 401),
отключённый (но выдававшийся) модуль читается (read-only, BIZ-61 срез-6).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.errors import api_problem_detail
from app.core.feature_flags import is_module_enabled, raise_for_disabled_module
from app.core.security import AccessContext, abac, rbac
from app.core.tenant_validation import TenantContextValidator
from app.models.ecology import (
    NVOS_CATEGORIES,
    NVOS_STATUSES,
    EnvironmentalFacility,
)
from app.models.master_data import Site
from app.models.models import Tenant
from app.schemas.ecology import (
    EcologyReadinessRead,
    EnvironmentalFacilityCreate,
    EnvironmentalFacilityPage,
    EnvironmentalFacilityRead,
    EnvironmentalFacilityUpdate,
)
from app.services.audit import AuditService, field_level_diff

router = APIRouter(prefix="/ecology", tags=["ecology"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_ROLES = ["admin", "owner", "ot_pb_lead", "ot_specialist"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


Access = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_ROLES, action="manage ecology")),
]

_FEATURE_CODE = "ecology"


async def _require_ecology(
    request: Request,
    session: SessionDep,
    tenant: TenantDep,
    _access: AccessContext = Depends(rbac(None)),
) -> None:
    """Гейт модуля — роутерная зависимость (каждый эндпоинт роутера)."""

    enabled = await is_module_enabled(session, str(tenant.id), _FEATURE_CODE)
    if not enabled:
        await raise_for_disabled_module(
            session,
            str(tenant.id),
            _FEATURE_CODE,
            request.method,
            error_type="ecology",
            disabled_code="ECOLOGY_DISABLED",
            disabled_message="Ecology module is not enabled for this tenant",
        )


router.dependencies.append(Depends(_require_ecology))


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(
            code="ECOLOGY_VALIDATION_ERROR", message=message, error_type="ecology"
        ),
    )


def _facility_read(facility: EnvironmentalFacility) -> EnvironmentalFacilityRead:
    return EnvironmentalFacilityRead(
        id=facility.id,
        name=facility.name,
        register_number=facility.register_number,
        category=facility.category,
        category_label=NVOS_CATEGORIES.get(facility.category, facility.category),
        site_id=facility.site_id,
        registered_on=facility.registered_on,
        actualized_on=facility.actualized_on,
        excluded_on=facility.excluded_on,
        status=facility.status,
        status_label=NVOS_STATUSES.get(facility.status, facility.status),
        responsible=facility.responsible,
        notes=facility.notes,
    )


async def _validate_site(session: AsyncSession, tenant: Tenant, site_id: str | None) -> None:
    if not site_id:
        return
    stmt = select(Site.id).where(
        Site.id == site_id,
        Site.tenant_id == tenant.id,
        Site.deleted_at.is_(None),
    )
    if (await session.execute(stmt)).scalar_one_or_none() is None:
        raise _unprocessable("Площадка не найдена")


def _validate_dictionaries(*, category: str | None, status_value: str | None) -> None:
    if category is not None and category not in NVOS_CATEGORIES:
        raise _unprocessable(
            f"Неизвестная категория {category!r}; допустимые: {', '.join(NVOS_CATEGORIES)}"
        )
    if status_value is not None and status_value not in NVOS_STATUSES:
        raise _unprocessable(
            f"Неизвестное состояние {status_value!r}; допустимые: {', '.join(NVOS_STATUSES)}"
        )


async def _ensure_register_number_free(
    session: AsyncSession, tenant: Tenant, register_number: str, *, exclude_id: str | None = None
) -> None:
    """Один код реестра — один объект.

    Дубль означает объект, заведённый дважды, и любой счёт по категориям стал
    бы враньём: одна площадка посчиталась бы за две.
    """

    stmt = select(EnvironmentalFacility.id).where(
        EnvironmentalFacility.tenant_id == tenant.id,
        EnvironmentalFacility.register_number == register_number,
        EnvironmentalFacility.deleted_at.is_(None),
    )
    if exclude_id:
        stmt = stmt.where(EnvironmentalFacility.id != exclude_id)
    if (await session.execute(stmt)).scalar_one_or_none() is not None:
        raise _unprocessable(f"Объект с кодом {register_number!r} уже заведён")


async def _get_facility_or_404(
    session: AsyncSession, tenant: Tenant, facility_id: str
) -> EnvironmentalFacility:
    stmt = select(EnvironmentalFacility).where(
        EnvironmentalFacility.id == facility_id,
        EnvironmentalFacility.tenant_id == tenant.id,
        EnvironmentalFacility.deleted_at.is_(None),
    )
    facility = (await session.execute(stmt)).scalar_one_or_none()
    if facility is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="NVOS_FACILITY_NOT_FOUND",
                message="Environmental facility not found",
                error_type="ecology",
            ),
        )
    return facility


@router.get("/facilities", response_model=EnvironmentalFacilityPage)
async def list_facilities(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    category: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    site_id: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> EnvironmentalFacilityPage:
    """Реестр объектов НВОС: что стоит на государственном учёте."""

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(EnvironmentalFacility).where(
        EnvironmentalFacility.tenant_id == tenant.id,
        EnvironmentalFacility.deleted_at.is_(None),
    )
    if category:
        stmt = stmt.where(EnvironmentalFacility.category == category)
    if status_filter:
        stmt = stmt.where(EnvironmentalFacility.status == status_filter)
    if site_id:
        stmt = stmt.where(EnvironmentalFacility.site_id == site_id)
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        (
            await session.execute(
                stmt.order_by(EnvironmentalFacility.category, EnvironmentalFacility.name)
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return EnvironmentalFacilityPage(
        items=[_facility_read(r) for r in rows], total=total
    )


@router.post(
    "/facilities",
    response_model=EnvironmentalFacilityRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_facility(
    request: Request,
    payload: EnvironmentalFacilityCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> EnvironmentalFacilityRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _validate_site(session, tenant, payload.site_id)
    _validate_dictionaries(category=payload.category, status_value=payload.status)
    register_number = payload.register_number.strip()
    await _ensure_register_number_free(session, tenant, register_number)

    facility = EnvironmentalFacility(
        tenant_id=str(tenant.id),
        name=payload.name.strip(),
        register_number=register_number,
        category=payload.category,
        site_id=payload.site_id,
        registered_on=payload.registered_on,
        actualized_on=payload.actualized_on,
        excluded_on=payload.excluded_on,
        status=payload.status or "registered",
        responsible=(payload.responsible or None),
        notes=(payload.notes or None),
    )
    session.add(facility)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="EnvironmentalFacility",
        object_id=facility.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": facility.id}}},
        details={
            "entity": "EnvironmentalFacility",
            "category": facility.category,
            "register_number": facility.register_number,
        },
    )
    await session.commit()
    await session.refresh(facility)
    return _facility_read(facility)


@router.patch("/facilities/{facility_id}", response_model=EnvironmentalFacilityRead)
async def update_facility(
    request: Request,
    facility_id: str,
    payload: EnvironmentalFacilityUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> EnvironmentalFacilityRead:
    """Актуализация сведений и снятие с учёта.

    Снятие с учёта — смена состояния, а НЕ удаление: история воздействия,
    отчётность и платежи остаются на месте.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    facility = await _get_facility_or_404(session, tenant, facility_id)
    data = payload.model_dump(exclude_unset=True)
    await _validate_site(session, tenant, data.get("site_id"))
    _validate_dictionaries(
        category=data.get("category"), status_value=data.get("status")
    )
    if "register_number" in data:
        value = data["register_number"]
        if value is None or not str(value).strip():
            raise _unprocessable("register_number cannot be empty")
        await _ensure_register_number_free(
            session, tenant, str(value).strip(), exclude_id=facility.id
        )

    before = _facility_read(facility).model_dump()
    for field in (
        "name",
        "register_number",
        "category",
        "site_id",
        "registered_on",
        "actualized_on",
        "excluded_on",
        "status",
        "responsible",
        "notes",
    ):
        if field in data:
            value = data[field]
            if field == "name" and (value is None or not str(value).strip()):
                raise _unprocessable("name cannot be empty")
            setattr(facility, field, value.strip() if isinstance(value, str) else value)
    after = _facility_read(facility).model_dump()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="EnvironmentalFacility",
        object_id=facility.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "EnvironmentalFacility"},
    )
    await session.commit()
    await session.refresh(facility)
    return _facility_read(facility)


@router.get("/readiness", response_model=EcologyReadinessRead)
async def ecology_readiness(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> EcologyReadinessRead:
    """Сколько объектов НВОС и какой категории.

    Считаются объекты НА УЧЁТЕ: снятый с учёта остаётся ради истории, но
    объектом надзора быть перестаёт. Ключи разреза — всегда все четыре
    категории, чтобы «ноль объектов I категории» отличался от «поле не
    пришло».

    ГРАНИЦА: платформа НЕ вычисляет категорию — её присваивают при постановке
    на учёт по критериям постановления Правительства, а исходных данных
    (мощность, виды воздействия, технологии) в системе нет.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    rows = (
        (
            await session.execute(
                select(EnvironmentalFacility).where(
                    EnvironmentalFacility.tenant_id == tenant.id,
                    EnvironmentalFacility.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    active = [r for r in rows if r.status == "registered"]
    by_category = {code: 0 for code in NVOS_CATEGORIES}
    for facility in active:
        if facility.category in by_category:
            by_category[facility.category] += 1
    return EcologyReadinessRead(
        total_facilities=len(active),
        by_category=by_category,
        excluded_facilities=len(rows) - len(active),
        # ФАКТ, а не нарушение: обязанность актуализировать сведения возникает
        # при изменении характеристик объекта, а не по календарю.
        never_actualized=sum(1 for r in active if r.actualized_on is None),
    )
