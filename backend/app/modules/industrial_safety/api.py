"""Контур ПромБеза, собственные ручки (Доп. №1 разд. 54.2, срез-1).

Реестр опасных производственных объектов: идентификация, класс опасности,
регистрационные сведения. До этого среза «ОПО» существовало тремя полями у
площадки, причём класс опасности был свободной строкой, перегруженной
категорией пожарной опасности — считать по классам было нечего.

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
from app.models.industrial_safety import (
    OPO_HAZARD_CLASSES,
    OPO_STATUSES,
    HazardousFacility,
)
from app.models.master_data import Site
from app.models.models import Tenant
from app.schemas.industrial_safety import (
    HazardousFacilityCreate,
    HazardousFacilityPage,
    HazardousFacilityRead,
    HazardousFacilityUpdate,
    IndustrialReadinessRead,
)
from app.services.audit import AuditService, field_level_diff

router = APIRouter(prefix="/industrial-safety", tags=["industrial-safety"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_ROLES = ["admin", "owner", "ot_pb_lead", "ot_specialist"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


Access = Annotated[
    AccessContext,
    Depends(
        abac(_tenant_resource_id, required_roles=_ROLES, action="manage industrial safety")
    ),
]

_FEATURE_CODE = "industrial_safety"


async def _require_industrial_safety(
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
            error_type="industrial_safety",
            disabled_code="INDUSTRIAL_SAFETY_DISABLED",
            disabled_message="Industrial safety module is not enabled for this tenant",
        )


router.dependencies.append(Depends(_require_industrial_safety))


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(
            code="INDUSTRIAL_SAFETY_VALIDATION_ERROR",
            message=message,
            error_type="industrial_safety",
        ),
    )


def _facility_read(facility: HazardousFacility) -> HazardousFacilityRead:
    return HazardousFacilityRead(
        id=facility.id,
        name=facility.name,
        register_number=facility.register_number,
        hazard_class=facility.hazard_class,
        hazard_class_label=OPO_HAZARD_CLASSES.get(
            facility.hazard_class, facility.hazard_class
        ),
        site_id=facility.site_id,
        registered_on=facility.registered_on,
        excluded_on=facility.excluded_on,
        status=facility.status,
        status_label=OPO_STATUSES.get(facility.status, facility.status),
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


def _validate_dictionaries(*, hazard_class: str | None, status_value: str | None) -> None:
    if hazard_class is not None and hazard_class not in OPO_HAZARD_CLASSES:
        raise _unprocessable(
            f"Неизвестный класс опасности {hazard_class!r}; допустимые: "
            f"{', '.join(OPO_HAZARD_CLASSES)}"
        )
    if status_value is not None and status_value not in OPO_STATUSES:
        raise _unprocessable(
            f"Неизвестное состояние {status_value!r}; допустимые: "
            f"{', '.join(OPO_STATUSES)}"
        )


async def _ensure_register_number_free(
    session: AsyncSession, tenant: Tenant, register_number: str, *, exclude_id: str | None = None
) -> None:
    """Один госномер — один объект.

    Дубль означает, что объект завели дважды, и любой счёт по классам стал бы
    враньём: одна котельная посчиталась бы за две.
    """

    stmt = select(HazardousFacility.id).where(
        HazardousFacility.tenant_id == tenant.id,
        HazardousFacility.register_number == register_number,
        HazardousFacility.deleted_at.is_(None),
    )
    if exclude_id:
        stmt = stmt.where(HazardousFacility.id != exclude_id)
    if (await session.execute(stmt)).scalar_one_or_none() is not None:
        raise _unprocessable(
            f"Объект с регистрационным номером {register_number!r} уже заведён"
        )


async def _get_facility_or_404(
    session: AsyncSession, tenant: Tenant, facility_id: str
) -> HazardousFacility:
    stmt = select(HazardousFacility).where(
        HazardousFacility.id == facility_id,
        HazardousFacility.tenant_id == tenant.id,
        HazardousFacility.deleted_at.is_(None),
    )
    facility = (await session.execute(stmt)).scalar_one_or_none()
    if facility is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="HAZARDOUS_FACILITY_NOT_FOUND",
                message="Hazardous production facility not found",
                error_type="industrial_safety",
            ),
        )
    return facility


@router.get("/facilities", response_model=HazardousFacilityPage)
async def list_facilities(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    hazard_class: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    site_id: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> HazardousFacilityPage:
    """Реестр ОПО: на одной площадке их может быть несколько."""

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(HazardousFacility).where(
        HazardousFacility.tenant_id == tenant.id,
        HazardousFacility.deleted_at.is_(None),
    )
    if hazard_class:
        stmt = stmt.where(HazardousFacility.hazard_class == hazard_class)
    if status_filter:
        stmt = stmt.where(HazardousFacility.status == status_filter)
    if site_id:
        stmt = stmt.where(HazardousFacility.site_id == site_id)
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        (
            await session.execute(
                stmt.order_by(HazardousFacility.hazard_class, HazardousFacility.name)
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return HazardousFacilityPage(
        items=[_facility_read(r) for r in rows], total=total
    )


@router.post(
    "/facilities",
    response_model=HazardousFacilityRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_facility(
    request: Request,
    payload: HazardousFacilityCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> HazardousFacilityRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _validate_site(session, tenant, payload.site_id)
    _validate_dictionaries(
        hazard_class=payload.hazard_class, status_value=payload.status
    )
    register_number = payload.register_number.strip()
    await _ensure_register_number_free(session, tenant, register_number)

    facility = HazardousFacility(
        tenant_id=str(tenant.id),
        name=payload.name.strip(),
        register_number=register_number,
        hazard_class=payload.hazard_class,
        site_id=payload.site_id,
        registered_on=payload.registered_on,
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
        object_type="HazardousFacility",
        object_id=facility.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": facility.id}}},
        details={
            "entity": "HazardousFacility",
            "hazard_class": facility.hazard_class,
            "register_number": facility.register_number,
        },
    )
    await session.commit()
    await session.refresh(facility)
    return _facility_read(facility)


@router.patch("/facilities/{facility_id}", response_model=HazardousFacilityRead)
async def update_facility(
    request: Request,
    facility_id: str,
    payload: HazardousFacilityUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> HazardousFacilityRead:
    """Правка сведений и исключение из госреестра.

    Исключение — смена состояния, а НЕ удаление: история эксплуатации,
    связанные документы и расследования остаются на месте.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    facility = await _get_facility_or_404(session, tenant, facility_id)
    data = payload.model_dump(exclude_unset=True)
    await _validate_site(session, tenant, data.get("site_id"))
    _validate_dictionaries(
        hazard_class=data.get("hazard_class"), status_value=data.get("status")
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
        "hazard_class",
        "site_id",
        "registered_on",
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
        object_type="HazardousFacility",
        object_id=facility.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "HazardousFacility"},
    )
    await session.commit()
    await session.refresh(facility)
    return _facility_read(facility)


@router.get("/readiness", response_model=IndustrialReadinessRead)
async def industrial_readiness(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> IndustrialReadinessRead:
    """Сколько ОПО и какого класса — от класса зависит режим надзора.

    Считаются ДЕЙСТВУЮЩИЕ объекты: исключённый из госреестра остаётся в
    системе ради истории, но объектом надзора быть перестаёт. Ключи разреза —
    всегда все четыре класса, чтобы «ноль объектов I класса» отличался от
    «поле не пришло».
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    rows = (
        (
            await session.execute(
                select(HazardousFacility).where(
                    HazardousFacility.tenant_id == tenant.id,
                    HazardousFacility.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    active = [r for r in rows if r.status == "registered"]
    by_class = {code: 0 for code in OPO_HAZARD_CLASSES}
    for facility in active:
        if facility.hazard_class in by_class:
            by_class[facility.hazard_class] += 1
    return IndustrialReadinessRead(
        total_facilities=len(active),
        by_class=by_class,
        excluded_facilities=len(rows) - len(active),
    )
