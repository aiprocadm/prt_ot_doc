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

import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.disciplines import Discipline, discipline_write_roles
from app.core.errors import api_problem_detail
from app.core.feature_flags import is_module_enabled, raise_for_disabled_module
from app.core.security import AccessContext, abac, rbac
from app.core.tenant_validation import TenantContextValidator
from app.models.ecology import (
    EMISSION_NORM_STATUS_TITLES,
    EMISSION_SOURCE_KINDS,
    FEE_IMPACT_KINDS,
    FEE_RATE_STATUS_TITLES,
    MEASUREMENT_COMPARISON_TITLES,
    MONITORING_STATUS_TITLES,
    MONTH_TITLES,
    NVOS_CATEGORIES,
    NVOS_STATUSES,
    PERIODICITY_LABELS,
    REPORTING_KINDS,
    REPORTING_STATUS_TITLES,
    WASTE_HAZARD_CLASSES,
    WASTE_MOVEMENT_KINDS,
    WATER_PERMIT_STATUS_TITLES,
    WATER_POINT_KINDS,
    WATER_RECORD_BASES,
    EcologyReportingDeadline,
    EmissionMeasurement,
    EmissionMonitoringPlanItem,
    EmissionNorm,
    EmissionSource,
    EnvironmentalFacility,
    NvosFeeLine,
    NvosFeeRate,
    WasteMovement,
    WastePassport,
    WaterUsagePoint,
    WaterUsageRecord,
)
from app.models.finance import Contract
from app.models.master_data import Site
from app.models.models import Tenant
from app.schemas.ecology import (
    EcologyReadinessRead,
    EcologyReportingDeadlineCreate,
    EcologyReportingDeadlinePage,
    EcologyReportingDeadlineRead,
    EcologyReportingDeadlineUpdate,
    EmissionMeasurementCreate,
    EmissionMeasurementPage,
    EmissionMeasurementRead,
    EmissionMeasurementUpdate,
    EmissionNormCreate,
    EmissionNormPage,
    EmissionNormRead,
    EmissionNormUpdate,
    EmissionSourceCreate,
    EmissionSourcePage,
    EmissionSourceRead,
    EmissionSourceUpdate,
    EnvironmentalFacilityCreate,
    EnvironmentalFacilityPage,
    EnvironmentalFacilityRead,
    EnvironmentalFacilityUpdate,
    MonitoringPlanItemCreate,
    MonitoringPlanItemPage,
    MonitoringPlanItemRead,
    MonitoringPlanItemUpdate,
    NvosFeeLineCreate,
    NvosFeeLinePage,
    NvosFeeLineRead,
    NvosFeeLineUpdate,
    NvosFeeRateCreate,
    NvosFeeRatePage,
    NvosFeeRateRead,
    NvosFeeRateUpdate,
    WasteContractPage,
    WasteContractRead,
    WasteMovementCreate,
    WasteMovementPage,
    WasteMovementRead,
    WasteMovementUpdate,
    WastePassportCreate,
    WastePassportPage,
    WastePassportRead,
    WastePassportUpdate,
    WaterUsagePointCreate,
    WaterUsagePointPage,
    WaterUsagePointRead,
    WaterUsagePointUpdate,
    WaterUsageRecordCreate,
    WaterUsageRecordPage,
    WaterUsageRecordRead,
    WaterUsageRecordUpdate,
)
from app.services.audit import AuditService, field_level_diff
from app.services.discipline_incidents import open_incidents_count

router = APIRouter(prefix="/ecology", tags=["ecology"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

#: Право на запись у контура — общее для всех дисциплин (срез-119):
#: один список в ядре вместо пяти одинаковых копий по модулям.
_ROLES = list(discipline_write_roles(Discipline.ECOLOGY))


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


async def _generated_this_year(
    session: AsyncSession, tenant: Tenant, passport_ids: list[str], year: int
) -> dict[str, Decimal]:
    """Образование за текущий год по каждому паспорту — одним запросом.

    Считается ПО ЖУРНАЛУ движений, а не хранится полем: сумма меняется с каждой
    записью, и хранимый итог разошёлся бы с журналом при первой же правке.
    """

    if not passport_ids:
        return {}
    rows = await session.execute(
        select(
            WasteMovement.passport_id,
            func.sum(WasteMovement.quantity_tons),
        )
        .where(
            WasteMovement.tenant_id == tenant.id,
            WasteMovement.deleted_at.is_(None),
            WasteMovement.passport_id.in_(passport_ids),
            WasteMovement.kind == "generated",
            WasteMovement.happened_on >= date(year, 1, 1),
            WasteMovement.happened_on <= date(year, 12, 31),
        )
        .group_by(WasteMovement.passport_id)
    )
    return {row[0]: Decimal(row[1] or 0) for row in rows}


def _passport_read(
    passport: WastePassport, generated: Decimal
) -> WastePassportRead:
    limit = passport.annual_limit_tons
    return WastePassportRead(
        id=passport.id,
        name=passport.name,
        fkko_code=passport.fkko_code,
        hazard_class=passport.hazard_class,
        hazard_class_label=WASTE_HAZARD_CLASSES.get(
            passport.hazard_class, passport.hazard_class
        ),
        facility_id=passport.facility_id,
        approved_on=passport.approved_on,
        annual_limit_tons=limit,
        notes=passport.notes,
        generated_this_year_tons=generated,
        # ГРАНИЦА: превышение считается ТОЛЬКО по внесённому лимиту. Платформа
        # лимит не рассчитывает — он берётся из НООЛР или декларации.
        over_limit=bool(limit is not None and generated > limit),
    )


def _movement_read(movement: WasteMovement) -> WasteMovementRead:
    return WasteMovementRead(
        id=movement.id,
        passport_id=movement.passport_id,
        kind=movement.kind,
        kind_label=WASTE_MOVEMENT_KINDS.get(movement.kind, movement.kind),
        happened_on=movement.happened_on,
        quantity_tons=movement.quantity_tons,
        contract_id=movement.contract_id,
        counterparty=movement.counterparty,
        notes=movement.notes,
    )


async def _get_passport_or_404(
    session: AsyncSession, tenant: Tenant, passport_id: str
) -> WastePassport:
    stmt = select(WastePassport).where(
        WastePassport.id == passport_id,
        WastePassport.tenant_id == tenant.id,
        WastePassport.deleted_at.is_(None),
    )
    passport = (await session.execute(stmt)).scalar_one_or_none()
    if passport is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="WASTE_PASSPORT_NOT_FOUND",
                message="Waste passport not found",
                error_type="ecology",
            ),
        )
    return passport


async def _get_movement_or_404(
    session: AsyncSession, tenant: Tenant, movement_id: str
) -> WasteMovement:
    stmt = select(WasteMovement).where(
        WasteMovement.id == movement_id,
        WasteMovement.tenant_id == tenant.id,
        WasteMovement.deleted_at.is_(None),
    )
    movement = (await session.execute(stmt)).scalar_one_or_none()
    if movement is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="WASTE_MOVEMENT_NOT_FOUND",
                message="Waste movement not found",
                error_type="ecology",
            ),
        )
    return movement


async def _ensure_fkko_free(
    session: AsyncSession, tenant: Tenant, fkko_code: str, *, exclude_id: str | None = None
) -> None:
    """Один код ФККО — один паспорт: дубль это вид отхода, заведённый дважды."""

    stmt = select(WastePassport.id).where(
        WastePassport.tenant_id == tenant.id,
        WastePassport.fkko_code == fkko_code,
        WastePassport.deleted_at.is_(None),
    )
    if exclude_id:
        stmt = stmt.where(WastePassport.id != exclude_id)
    if (await session.execute(stmt)).scalar_one_or_none() is not None:
        raise _unprocessable(f"Паспорт на код ФККО {fkko_code!r} уже заведён")


async def _validate_facility(
    session: AsyncSession, tenant: Tenant, facility_id: str | None
) -> None:
    if not facility_id:
        return
    stmt = select(EnvironmentalFacility.id).where(
        EnvironmentalFacility.id == facility_id,
        EnvironmentalFacility.tenant_id == tenant.id,
        EnvironmentalFacility.deleted_at.is_(None),
    )
    if (await session.execute(stmt)).scalar_one_or_none() is None:
        raise _unprocessable("Объект НВОС не найден")


@router.get("/waste-passports", response_model=WastePassportPage)
async def list_waste_passports(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    hazard_class: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> WastePassportPage:
    """Паспорта отходов I–IV класса с образованием за текущий год."""

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(WastePassport).where(
        WastePassport.tenant_id == tenant.id,
        WastePassport.deleted_at.is_(None),
    )
    if hazard_class:
        stmt = stmt.where(WastePassport.hazard_class == hazard_class)
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        (
            await session.execute(
                stmt.order_by(WastePassport.hazard_class, WastePassport.name)
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    generated = await _generated_this_year(
        session, tenant, [r.id for r in rows], date.today().year
    )
    return WastePassportPage(
        items=[
            _passport_read(r, generated.get(r.id, Decimal("0.000"))) for r in rows
        ],
        total=total,
    )


@router.post(
    "/waste-passports", response_model=WastePassportRead, status_code=status.HTTP_201_CREATED
)
async def create_waste_passport(
    request: Request,
    payload: WastePassportCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> WastePassportRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    if payload.hazard_class not in WASTE_HAZARD_CLASSES:
        raise _unprocessable(
            f"Неизвестный класс опасности {payload.hazard_class!r}; допустимые: "
            f"{', '.join(WASTE_HAZARD_CLASSES)} (отходы V класса паспортизации "
            "не подлежат)"
        )
    await _validate_facility(session, tenant, payload.facility_id)
    fkko_code = payload.fkko_code.strip()
    await _ensure_fkko_free(session, tenant, fkko_code)

    passport = WastePassport(
        tenant_id=str(tenant.id),
        name=payload.name.strip(),
        fkko_code=fkko_code,
        hazard_class=payload.hazard_class,
        facility_id=payload.facility_id,
        approved_on=payload.approved_on,
        annual_limit_tons=payload.annual_limit_tons,
        notes=(payload.notes or None),
    )
    session.add(passport)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="WastePassport",
        object_id=passport.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": passport.id}}},
        details={"entity": "WastePassport", "fkko_code": passport.fkko_code},
    )
    await session.commit()
    await session.refresh(passport)
    return _passport_read(passport, Decimal("0.000"))


@router.patch("/waste-passports/{passport_id}", response_model=WastePassportRead)
async def update_waste_passport(
    request: Request,
    passport_id: str,
    payload: WastePassportUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> WastePassportRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    passport = await _get_passport_or_404(session, tenant, passport_id)
    data = payload.model_dump(exclude_unset=True)
    if "hazard_class" in data and data["hazard_class"] not in WASTE_HAZARD_CLASSES:
        raise _unprocessable(
            f"Неизвестный класс опасности {data['hazard_class']!r}; допустимые: "
            f"{', '.join(WASTE_HAZARD_CLASSES)}"
        )
    await _validate_facility(session, tenant, data.get("facility_id"))
    if "fkko_code" in data and data["fkko_code"]:
        await _ensure_fkko_free(
            session, tenant, str(data["fkko_code"]).strip(), exclude_id=passport.id
        )

    year = date.today().year
    generated_before = await _generated_this_year(session, tenant, [passport.id], year)
    before = _passport_read(
        passport, generated_before.get(passport.id, Decimal("0.000"))
    ).model_dump()
    for field in (
        "name",
        "fkko_code",
        "hazard_class",
        "facility_id",
        "approved_on",
        "annual_limit_tons",
        "notes",
    ):
        if field in data:
            value = data[field]
            if field == "name" and (value is None or not str(value).strip()):
                raise _unprocessable("name cannot be empty")
            setattr(passport, field, value.strip() if isinstance(value, str) else value)
    generated = generated_before.get(passport.id, Decimal("0.000"))
    after = _passport_read(passport, generated).model_dump()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="WastePassport",
        object_id=passport.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "WastePassport"},
    )
    await session.commit()
    await session.refresh(passport)
    return _passport_read(passport, generated)


@router.get("/waste-movements", response_model=WasteMovementPage)
async def list_waste_movements(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    passport_id: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> WasteMovementPage:
    """Журнал учёта отходов: список движений по паспорту.

    Это и есть «журнал учёта отходов» из ТЗ: ядровой ``Journal`` не подходит —
    у его записи ``person_id`` NOT NULL, а движение отходов к человеку не
    привязано.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(WasteMovement).where(
        WasteMovement.tenant_id == tenant.id,
        WasteMovement.deleted_at.is_(None),
    )
    if passport_id:
        stmt = stmt.where(WasteMovement.passport_id == passport_id)
    if kind:
        stmt = stmt.where(WasteMovement.kind == kind)
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        (
            await session.execute(
                stmt.order_by(
                    WasteMovement.happened_on.desc(), WasteMovement.created_at.desc()
                )
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return WasteMovementPage(items=[_movement_read(r) for r in rows], total=total)


@router.get("/waste-contracts", response_model=WasteContractPage)
async def list_waste_contracts(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> WasteContractPage:
    """Договоры арендатора — для выбора в записи журнала учёта отходов.

    ПОЧЕМУ СВОЯ РУЧКА, А НЕ ЯДРОВАЯ ``/contracts`` (срез-112). Требование
    разд. 55.2 «договоры с операторами» упиралось не в данные — поле
    ``contract_id`` у движения есть со среза-2, — а в ДОСТУП: ядровой реестр
    договоров закрыт ролями бухгалтерии (admin/owner/accountant) и отдаёт
    суммы и валюту. Пустить туда эколога значило бы открыть ему финансовые
    условия ради выпадающего списка; выдать ему роль бухгалтера — тем более.
    Поэтому здесь отдаются ТОЛЬКО контрагент, номер, срок и состояние — ровно
    то, чем договор называют в журнале, — и ручка живёт под гейтом модуля
    экологии с ролями контура.

    ГРАНИЦА: платформа не решает, какой договор «правильный» для этого отхода,
    и не фильтрует список по виду отхода — связи «оператор ↔ ФККО» в данных
    нет. Закрытые и расторгнутые договоры остаются в списке: движение могло
    произойти, пока договор действовал.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(Contract).where(
        Contract.tenant_id == tenant.id,
        Contract.deleted_at.is_(None),
    )
    total = int(
        await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )
    rows = (
        (
            await session.execute(
                stmt.order_by(Contract.counterparty_name, Contract.contract_number)
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return WasteContractPage(
        items=[
            WasteContractRead(
                id=row.id,
                counterparty_name=row.counterparty_name,
                contract_number=row.contract_number,
                valid_until=row.valid_until,
                status=row.status.value if hasattr(row.status, "value") else str(row.status),
            )
            for row in rows
        ],
        total=total,
    )


@router.post(
    "/waste-movements", response_model=WasteMovementRead, status_code=status.HTTP_201_CREATED
)
async def create_waste_movement(
    request: Request,
    payload: WasteMovementCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> WasteMovementRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    passport = (
        await session.execute(
            select(WastePassport.id).where(
                WastePassport.id == payload.passport_id,
                WastePassport.tenant_id == tenant.id,
                WastePassport.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if passport is None:
        raise _unprocessable("Паспорт не найден")
    if payload.kind not in WASTE_MOVEMENT_KINDS:
        raise _unprocessable(
            f"Неизвестный вид движения {payload.kind!r}; допустимые: "
            f"{', '.join(WASTE_MOVEMENT_KINDS)}"
        )
    if payload.happened_on > date.today():
        raise _unprocessable(
            "Дата движения не может быть в будущем — журнал учёта фиксирует "
            "свершившееся, а не планируемое"
        )
    if payload.contract_id:
        contract = (
            await session.execute(
                select(Contract.id).where(
                    Contract.id == payload.contract_id,
                    Contract.tenant_id == tenant.id,
                    Contract.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if contract is None:
            raise _unprocessable("Договор не найден")

    movement = WasteMovement(
        tenant_id=str(tenant.id),
        passport_id=payload.passport_id,
        kind=payload.kind,
        happened_on=payload.happened_on,
        quantity_tons=payload.quantity_tons,
        contract_id=payload.contract_id,
        counterparty=(payload.counterparty or None),
        notes=(payload.notes or None),
    )
    session.add(movement)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="WasteMovement",
        object_id=movement.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": movement.id}}},
        details={"entity": "WasteMovement", "kind": movement.kind},
    )
    await session.commit()
    await session.refresh(movement)
    return _movement_read(movement)


@router.patch("/waste-movements/{movement_id}", response_model=WasteMovementRead)
async def update_waste_movement(
    request: Request,
    movement_id: str,
    payload: WasteMovementUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> WasteMovementRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    movement = await _get_movement_or_404(session, tenant, movement_id)
    data = payload.model_dump(exclude_unset=True)
    if "kind" in data and data["kind"] not in WASTE_MOVEMENT_KINDS:
        raise _unprocessable(
            f"Неизвестный вид движения {data['kind']!r}; допустимые: "
            f"{', '.join(WASTE_MOVEMENT_KINDS)}"
        )
    next_date = data["happened_on"] if "happened_on" in data else movement.happened_on
    if next_date > date.today():
        raise _unprocessable("Дата движения не может быть в будущем")

    before = _movement_read(movement).model_dump()
    for field in (
        "passport_id",
        "kind",
        "happened_on",
        "quantity_tons",
        "contract_id",
        "counterparty",
        "notes",
    ):
        if field in data:
            value = data[field]
            setattr(movement, field, value.strip() if isinstance(value, str) else value)
    after = _movement_read(movement).model_dump()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="WasteMovement",
        object_id=movement.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "WasteMovement"},
    )
    await session.commit()
    await session.refresh(movement)
    return _movement_read(movement)


#: горизонт «скоро истекает» для разрешений — тот же, что у остальных сводок
_DUE_SOON_DAYS = 30


def _norm_status(valid_until: date | None, today: date) -> str:
    """Состояние разрешения — считается ПРИ ЧТЕНИИ.

    Пустой срок означает БЕССРОЧНО, а не «просрочено»: для объектов III
    категории нормативы могут действовать без срока (прецедент срока
    пересмотра документов ПБ).
    """

    if valid_until is None:
        return "ok"
    if valid_until < today:
        return "overdue"
    if valid_until <= today + timedelta(days=_DUE_SOON_DAYS):
        return "due_soon"
    return "ok"


def _source_read(source: EmissionSource, norms_count: int) -> EmissionSourceRead:
    return EmissionSourceRead(
        id=source.id,
        facility_id=source.facility_id,
        source_number=source.source_number,
        name=source.name,
        kind=source.kind,
        kind_label=EMISSION_SOURCE_KINDS.get(source.kind, source.kind),
        location=source.location,
        inventoried_on=source.inventoried_on,
        notes=source.notes,
        norms_count=norms_count,
    )


def _norm_read(norm: EmissionNorm, today: date) -> EmissionNormRead:
    status_value = _norm_status(norm.valid_until, today)
    return EmissionNormRead(
        id=norm.id,
        source_id=norm.source_id,
        substance=norm.substance,
        limit_grams_per_second=norm.limit_grams_per_second,
        limit_tons_per_year=norm.limit_tons_per_year,
        permit_number=norm.permit_number,
        valid_until=norm.valid_until,
        notes=norm.notes,
        validity_status=status_value,
        validity_status_label=EMISSION_NORM_STATUS_TITLES.get(
            status_value, status_value
        ),
    )


async def _norms_count_map(
    session: AsyncSession, tenant: Tenant, source_ids: list[str]
) -> dict[str, int]:
    """Сколько нормативов у каждого источника — одним запросом, а не N+1."""

    if not source_ids:
        return {}
    rows = await session.execute(
        select(EmissionNorm.source_id, func.count())
        .where(
            EmissionNorm.tenant_id == tenant.id,
            EmissionNorm.deleted_at.is_(None),
            EmissionNorm.source_id.in_(source_ids),
        )
        .group_by(EmissionNorm.source_id)
    )
    return {row[0]: int(row[1]) for row in rows}


async def _get_source_or_404(
    session: AsyncSession, tenant: Tenant, source_id: str
) -> EmissionSource:
    stmt = select(EmissionSource).where(
        EmissionSource.id == source_id,
        EmissionSource.tenant_id == tenant.id,
        EmissionSource.deleted_at.is_(None),
    )
    source = (await session.execute(stmt)).scalar_one_or_none()
    if source is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="EMISSION_SOURCE_NOT_FOUND",
                message="Emission source not found",
                error_type="ecology",
            ),
        )
    return source


async def _get_norm_or_404(
    session: AsyncSession, tenant: Tenant, norm_id: str
) -> EmissionNorm:
    stmt = select(EmissionNorm).where(
        EmissionNorm.id == norm_id,
        EmissionNorm.tenant_id == tenant.id,
        EmissionNorm.deleted_at.is_(None),
    )
    norm = (await session.execute(stmt)).scalar_one_or_none()
    if norm is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="EMISSION_NORM_NOT_FOUND",
                message="Emission norm not found",
                error_type="ecology",
            ),
        )
    return norm


async def _ensure_source_number_free(
    session: AsyncSession,
    tenant: Tenant,
    facility_id: str,
    source_number: str,
    *,
    exclude_id: str | None = None,
) -> None:
    """Номер уникален В ПРЕДЕЛАХ ОБЪЕКТА: «источник №1» есть у каждого."""

    stmt = select(EmissionSource.id).where(
        EmissionSource.tenant_id == tenant.id,
        EmissionSource.facility_id == facility_id,
        EmissionSource.source_number == source_number,
        EmissionSource.deleted_at.is_(None),
    )
    if exclude_id:
        stmt = stmt.where(EmissionSource.id != exclude_id)
    if (await session.execute(stmt)).scalar_one_or_none() is not None:
        raise _unprocessable(
            f"Источник с номером {source_number!r} на этом объекте уже заведён"
        )


@router.get("/emission-sources", response_model=EmissionSourcePage)
async def list_emission_sources(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    facility_id: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> EmissionSourcePage:
    """Инвентаризация стационарных источников выбросов."""

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(EmissionSource).where(
        EmissionSource.tenant_id == tenant.id,
        EmissionSource.deleted_at.is_(None),
    )
    if facility_id:
        stmt = stmt.where(EmissionSource.facility_id == facility_id)
    if kind:
        stmt = stmt.where(EmissionSource.kind == kind)
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        (
            await session.execute(
                stmt.order_by(EmissionSource.source_number).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    counts = await _norms_count_map(session, tenant, [r.id for r in rows])
    return EmissionSourcePage(
        items=[_source_read(r, counts.get(r.id, 0)) for r in rows], total=total
    )


@router.post(
    "/emission-sources",
    response_model=EmissionSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_emission_source(
    request: Request,
    payload: EmissionSourceCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> EmissionSourceRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _validate_facility(session, tenant, payload.facility_id)
    if payload.kind not in EMISSION_SOURCE_KINDS:
        raise _unprocessable(
            f"Неизвестный тип источника {payload.kind!r}; допустимые: "
            f"{', '.join(EMISSION_SOURCE_KINDS)}"
        )
    source_number = payload.source_number.strip()
    await _ensure_source_number_free(
        session, tenant, payload.facility_id, source_number
    )

    source = EmissionSource(
        tenant_id=str(tenant.id),
        facility_id=payload.facility_id,
        source_number=source_number,
        name=payload.name.strip(),
        kind=payload.kind,
        location=(payload.location or None),
        inventoried_on=payload.inventoried_on,
        notes=(payload.notes or None),
    )
    session.add(source)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="EmissionSource",
        object_id=source.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": source.id}}},
        details={"entity": "EmissionSource", "source_number": source.source_number},
    )
    await session.commit()
    await session.refresh(source)
    return _source_read(source, 0)


@router.patch("/emission-sources/{source_id}", response_model=EmissionSourceRead)
async def update_emission_source(
    request: Request,
    source_id: str,
    payload: EmissionSourceUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> EmissionSourceRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    source = await _get_source_or_404(session, tenant, source_id)
    data = payload.model_dump(exclude_unset=True)
    await _validate_facility(session, tenant, data.get("facility_id"))
    if "kind" in data and data["kind"] not in EMISSION_SOURCE_KINDS:
        raise _unprocessable(
            f"Неизвестный тип источника {data['kind']!r}; допустимые: "
            f"{', '.join(EMISSION_SOURCE_KINDS)}"
        )
    next_facility = data.get("facility_id") or source.facility_id
    if "source_number" in data or "facility_id" in data:
        number = str(data.get("source_number") or source.source_number).strip()
        await _ensure_source_number_free(
            session, tenant, next_facility, number, exclude_id=source.id
        )

    counts = await _norms_count_map(session, tenant, [source.id])
    before = _source_read(source, counts.get(source.id, 0)).model_dump()
    for field in (
        "facility_id",
        "source_number",
        "name",
        "kind",
        "location",
        "inventoried_on",
        "notes",
    ):
        if field in data:
            value = data[field]
            if field in {"name", "source_number"} and (
                value is None or not str(value).strip()
            ):
                raise _unprocessable(f"{field} cannot be empty")
            setattr(source, field, value.strip() if isinstance(value, str) else value)
    after = _source_read(source, counts.get(source.id, 0)).model_dump()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="EmissionSource",
        object_id=source.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "EmissionSource"},
    )
    await session.commit()
    await session.refresh(source)
    return _source_read(source, counts.get(source.id, 0))


@router.get("/emission-norms", response_model=EmissionNormPage)
async def list_emission_norms(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    source_id: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> EmissionNormPage:
    """Нормативы выбросов по веществам с состоянием разрешения."""

    TenantContextValidator.ensure_tenant_context(tenant)
    today = date.today()
    stmt = select(EmissionNorm).where(
        EmissionNorm.tenant_id == tenant.id,
        EmissionNorm.deleted_at.is_(None),
    )
    if source_id:
        stmt = stmt.where(EmissionNorm.source_id == source_id)
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        (
            await session.execute(
                stmt.order_by(EmissionNorm.substance).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return EmissionNormPage(items=[_norm_read(r, today) for r in rows], total=total)


@router.post(
    "/emission-norms", response_model=EmissionNormRead, status_code=status.HTTP_201_CREATED
)
async def create_emission_norm(
    request: Request,
    payload: EmissionNormCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> EmissionNormRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_source_or_404(session, tenant, payload.source_id)
    if (
        payload.limit_grams_per_second is None
        and payload.limit_tons_per_year is None
    ):
        raise _unprocessable(
            "Нужно хотя бы одно значение норматива: разовый (г/с) или валовый "
            "(т/год) — норматив без значений ничего не нормирует"
        )
    substance = payload.substance.strip()
    duplicate = (
        await session.execute(
            select(EmissionNorm.id).where(
                EmissionNorm.tenant_id == tenant.id,
                EmissionNorm.source_id == payload.source_id,
                EmissionNorm.substance == substance,
                EmissionNorm.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise _unprocessable(
            f"Норматив по веществу {substance!r} для этого источника уже задан"
        )

    norm = EmissionNorm(
        tenant_id=str(tenant.id),
        source_id=payload.source_id,
        substance=substance,
        limit_grams_per_second=payload.limit_grams_per_second,
        limit_tons_per_year=payload.limit_tons_per_year,
        permit_number=(payload.permit_number or None),
        valid_until=payload.valid_until,
        notes=(payload.notes or None),
    )
    session.add(norm)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="EmissionNorm",
        object_id=norm.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": norm.id}}},
        details={"entity": "EmissionNorm", "substance": norm.substance},
    )
    await session.commit()
    await session.refresh(norm)
    return _norm_read(norm, date.today())


@router.patch("/emission-norms/{norm_id}", response_model=EmissionNormRead)
async def update_emission_norm(
    request: Request,
    norm_id: str,
    payload: EmissionNormUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> EmissionNormRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    norm = await _get_norm_or_404(session, tenant, norm_id)
    data = payload.model_dump(exclude_unset=True)
    if "source_id" in data and data["source_id"]:
        await _get_source_or_404(session, tenant, str(data["source_id"]))

    today = date.today()
    before = _norm_read(norm, today).model_dump()
    for field in (
        "source_id",
        "substance",
        "limit_grams_per_second",
        "limit_tons_per_year",
        "permit_number",
        "valid_until",
        "notes",
    ):
        if field in data:
            value = data[field]
            if field == "substance" and (value is None or not str(value).strip()):
                raise _unprocessable("substance cannot be empty")
            setattr(norm, field, value.strip() if isinstance(value, str) else value)
    # Проверяем ИТОГОВОЕ состояние: норматив не должен остаться без значений.
    if norm.limit_grams_per_second is None and norm.limit_tons_per_year is None:
        raise _unprocessable(
            "Нужно хотя бы одно значение норматива: разовый (г/с) или валовый "
            "(т/год)"
        )
    after = _norm_read(norm, today).model_dump()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="EmissionNorm",
        object_id=norm.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "EmissionNorm"},
    )
    await session.commit()
    await session.refresh(norm)
    return _norm_read(norm, date.today())


# --- ПЭК: план-график замеров и сами замеры (разд. 55.2) --------------------


def _add_months(value: date, months: int) -> date:
    """Прибавить месяцы, не выпав за край короткого месяца (31.01 + 1 = 28.02).

    Свой четырёхстрочник вместо импорта из контура обучения: ходить за
    арифметикой в чужой модуль — это связь, которую потом нечем оправдать
    (тот же довод, что и в контуре пожарной безопасности).
    """

    target = value.month - 1 + months
    year = value.year + target // 12
    month = target % 12 + 1
    return value.replace(
        year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1])
    )


def _periodicity_label(months: int) -> str:
    """«раз в квартал» для привычных сроков, «раз в N месяцев» — для прочих."""

    known = PERIODICITY_LABELS.get(months)
    if known:
        return known
    return f"раз в {months} месяца" if 2 <= months <= 4 else f"раз в {months} месяцев"


def _monitoring_status(next_due_on: date, today: date) -> str:
    """Состояние строки плана — считается ПРИ ЧТЕНИИ по плановой дате."""

    if next_due_on < today:
        return "overdue"
    if next_due_on <= today + timedelta(days=_DUE_SOON_DAYS):
        return "due_soon"
    return "ok"


def _plan_read(
    item: EmissionMonitoringPlanItem, last_measured_on: date | None, today: date
) -> MonitoringPlanItemRead:
    status_value = _monitoring_status(item.next_due_on, today)
    return MonitoringPlanItemRead(
        id=item.id,
        source_id=item.source_id,
        substance=item.substance,
        periodicity_months=item.periodicity_months,
        periodicity_label=_periodicity_label(item.periodicity_months),
        next_due_on=item.next_due_on,
        method=item.method,
        laboratory=item.laboratory,
        notes=item.notes,
        status=status_value,
        status_label=MONITORING_STATUS_TITLES.get(status_value, status_value),
        last_measured_on=last_measured_on,
    )


async def _last_measured_map(
    session: AsyncSession, tenant: Tenant, plan_ids: list[str]
) -> dict[str, date]:
    """Дата последнего замера по каждой строке плана — одним запросом."""

    if not plan_ids:
        return {}
    rows = await session.execute(
        select(EmissionMeasurement.plan_id, func.max(EmissionMeasurement.measured_on))
        .where(
            EmissionMeasurement.tenant_id == tenant.id,
            EmissionMeasurement.deleted_at.is_(None),
            EmissionMeasurement.plan_id.in_(plan_ids),
        )
        .group_by(EmissionMeasurement.plan_id)
    )
    return {row[0]: row[1] for row in rows if row[0] and row[1]}


async def _norm_for_pair(
    session: AsyncSession, tenant: Tenant, source_id: str, substance: str
) -> EmissionNorm | None:
    stmt = select(EmissionNorm).where(
        EmissionNorm.tenant_id == tenant.id,
        EmissionNorm.source_id == source_id,
        EmissionNorm.substance == substance,
        EmissionNorm.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _norms_by_pair(
    session: AsyncSession, tenant: Tenant
) -> dict[tuple[str, str], EmissionNorm]:
    """Нормативы по парам «источник + вещество» — одним запросом, а не N+1."""

    rows = (
        (
            await session.execute(
                select(EmissionNorm).where(
                    EmissionNorm.tenant_id == tenant.id,
                    EmissionNorm.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    return {(n.source_id, n.substance): n for n in rows}


def _comparison(value: Decimal, norm: EmissionNorm | None) -> tuple[str, Decimal | None]:
    """Сравнение замера с разовым нормативом — ФАКТ по двум внесённым числам.

    Нет норматива — «норматив не внесён», а НЕ «превышение»: молчание о
    нормативе нельзя выдавать за нарушение. Валовый норматив (т/год) с разовым
    замером (г/с) несопоставим, и делать вид, что сопоставим, нельзя: это
    разные величины, а не разные единицы одной.
    """

    if norm is None:
        return "no_norm", None
    if norm.limit_grams_per_second is None:
        return "no_single_limit", None
    if value > norm.limit_grams_per_second:
        return "exceeded", norm.limit_grams_per_second
    return "within", norm.limit_grams_per_second


def _measurement_read(
    measurement: EmissionMeasurement, norm: EmissionNorm | None
) -> EmissionMeasurementRead:
    verdict, limit = _comparison(measurement.value_grams_per_second, norm)
    return EmissionMeasurementRead(
        id=measurement.id,
        plan_id=measurement.plan_id,
        source_id=measurement.source_id,
        substance=measurement.substance,
        measured_on=measurement.measured_on,
        value_grams_per_second=measurement.value_grams_per_second,
        protocol_number=measurement.protocol_number,
        laboratory=measurement.laboratory,
        notes=measurement.notes,
        norm_grams_per_second=limit,
        comparison=verdict,
        comparison_label=MEASUREMENT_COMPARISON_TITLES.get(verdict, verdict),
    )


async def _get_plan_or_404(
    session: AsyncSession, tenant: Tenant, plan_id: str
) -> EmissionMonitoringPlanItem:
    stmt = select(EmissionMonitoringPlanItem).where(
        EmissionMonitoringPlanItem.id == plan_id,
        EmissionMonitoringPlanItem.tenant_id == tenant.id,
        EmissionMonitoringPlanItem.deleted_at.is_(None),
    )
    item = (await session.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="MONITORING_PLAN_ITEM_NOT_FOUND",
                message="Monitoring plan item not found",
                error_type="ecology",
            ),
        )
    return item


async def _get_measurement_or_404(
    session: AsyncSession, tenant: Tenant, measurement_id: str
) -> EmissionMeasurement:
    stmt = select(EmissionMeasurement).where(
        EmissionMeasurement.id == measurement_id,
        EmissionMeasurement.tenant_id == tenant.id,
        EmissionMeasurement.deleted_at.is_(None),
    )
    measurement = (await session.execute(stmt)).scalar_one_or_none()
    if measurement is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="EMISSION_MEASUREMENT_NOT_FOUND",
                message="Emission measurement not found",
                error_type="ecology",
            ),
        )
    return measurement


async def _ensure_plan_pair_free(
    session: AsyncSession,
    tenant: Tenant,
    source_id: str,
    substance: str,
    *,
    exclude_id: str | None = None,
) -> None:
    """Одна строка графика на пару «источник + вещество».

    Две строки означали бы два разных графика на одно и то же вещество, и по
    какому из них считать просрочку — было бы неизвестно.
    """

    stmt = select(EmissionMonitoringPlanItem.id).where(
        EmissionMonitoringPlanItem.tenant_id == tenant.id,
        EmissionMonitoringPlanItem.source_id == source_id,
        EmissionMonitoringPlanItem.substance == substance,
        EmissionMonitoringPlanItem.deleted_at.is_(None),
    )
    if exclude_id:
        stmt = stmt.where(EmissionMonitoringPlanItem.id != exclude_id)
    if (await session.execute(stmt)).scalar_one_or_none() is not None:
        raise _unprocessable(
            f"Строка графика по веществу {substance!r} на этом источнике уже заведена"
        )


def _advance_plan_due(item: EmissionMonitoringPlanItem, measured_on: date) -> None:
    """Сдвинуть плановую дату: замер закрыл текущий цикл графика.

    Сдвиг идёт ПО СЕТКЕ (от прежней плановой даты, а не от даты замера):
    календарная сетка ПЭК не должна сбиваться из-за одного опоздания.

    Первый шаг делается ВСЕГДА, а не только когда срок уже прошёл: замер,
    сделанный на неделю раньше плана, тоже закрывает цикл — иначе график
    продолжал бы требовать замер, который уже лежит в системе.

    Замер ЗАДНИМ ЧИСЛОМ (раньше начала текущего цикла) график не двигает: это
    внесение старых данных, а не выполнение ближайшего замера.
    """

    cycle_start = _add_months(item.next_due_on, -item.periodicity_months)
    if measured_on < cycle_start:
        return
    due = _add_months(item.next_due_on, item.periodicity_months)
    while due <= measured_on:
        due = _add_months(due, item.periodicity_months)
    item.next_due_on = due


@router.get("/monitoring-plan", response_model=MonitoringPlanItemPage)
async def list_monitoring_plan(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    source_id: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> MonitoringPlanItemPage:
    """План-график замеров ПЭК: пары «источник + вещество» и сроки."""

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(EmissionMonitoringPlanItem).where(
        EmissionMonitoringPlanItem.tenant_id == tenant.id,
        EmissionMonitoringPlanItem.deleted_at.is_(None),
    )
    if source_id:
        stmt = stmt.where(EmissionMonitoringPlanItem.source_id == source_id)
    total = int(
        await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )
    rows = (
        (
            await session.execute(
                stmt.order_by(EmissionMonitoringPlanItem.next_due_on)
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    measured = await _last_measured_map(session, tenant, [r.id for r in rows])
    today = date.today()
    return MonitoringPlanItemPage(
        items=[_plan_read(r, measured.get(r.id), today) for r in rows], total=total
    )


@router.post(
    "/monitoring-plan",
    response_model=MonitoringPlanItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_monitoring_plan_item(
    request: Request,
    payload: MonitoringPlanItemCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> MonitoringPlanItemRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_source_or_404(session, tenant, payload.source_id)
    substance = payload.substance.strip()
    await _ensure_plan_pair_free(session, tenant, payload.source_id, substance)

    item = EmissionMonitoringPlanItem(
        tenant_id=str(tenant.id),
        source_id=payload.source_id,
        substance=substance,
        periodicity_months=payload.periodicity_months,
        next_due_on=payload.next_due_on,
        method=(payload.method or None),
        laboratory=(payload.laboratory or None),
        notes=(payload.notes or None),
    )
    session.add(item)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="EmissionMonitoringPlanItem",
        object_id=item.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": item.id}}},
        details={"entity": "EmissionMonitoringPlanItem", "substance": item.substance},
    )
    await session.commit()
    await session.refresh(item)
    return _plan_read(item, None, date.today())


@router.patch("/monitoring-plan/{item_id}", response_model=MonitoringPlanItemRead)
async def update_monitoring_plan_item(
    request: Request,
    item_id: str,
    payload: MonitoringPlanItemUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> MonitoringPlanItemRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    item = await _get_plan_or_404(session, tenant, item_id)
    before = {
        "substance": item.substance,
        "periodicity_months": item.periodicity_months,
        "next_due_on": str(item.next_due_on),
        "method": item.method,
        "laboratory": item.laboratory,
        "notes": item.notes,
    }
    data = payload.model_dump(exclude_unset=True)
    if data.get("substance"):
        substance = str(data["substance"]).strip()
        await _ensure_plan_pair_free(
            session, tenant, item.source_id, substance, exclude_id=item.id
        )
        item.substance = substance
    if data.get("periodicity_months") is not None:
        item.periodicity_months = int(data["periodicity_months"])
    if data.get("next_due_on") is not None:
        item.next_due_on = data["next_due_on"]
    for field in ("method", "laboratory", "notes"):
        if field in data:
            setattr(item, field, data[field] or None)
    await session.flush()
    after = {
        "substance": item.substance,
        "periodicity_months": item.periodicity_months,
        "next_due_on": str(item.next_due_on),
        "method": item.method,
        "laboratory": item.laboratory,
        "notes": item.notes,
    }
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="EmissionMonitoringPlanItem",
        object_id=item.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "EmissionMonitoringPlanItem"},
    )
    await session.commit()
    await session.refresh(item)
    measured = await _last_measured_map(session, tenant, [item.id])
    return _plan_read(item, measured.get(item.id), date.today())


@router.get("/emission-measurements", response_model=EmissionMeasurementPage)
async def list_emission_measurements(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    source_id: str | None = Query(default=None),
    plan_id: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> EmissionMeasurementPage:
    """Замеры ПЭК вместе с итогом сравнения с нормативом."""

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(EmissionMeasurement).where(
        EmissionMeasurement.tenant_id == tenant.id,
        EmissionMeasurement.deleted_at.is_(None),
    )
    if source_id:
        stmt = stmt.where(EmissionMeasurement.source_id == source_id)
    if plan_id:
        stmt = stmt.where(EmissionMeasurement.plan_id == plan_id)
    total = int(
        await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )
    rows = (
        (
            await session.execute(
                stmt.order_by(EmissionMeasurement.measured_on.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    norms = await _norms_by_pair(session, tenant)
    return EmissionMeasurementPage(
        items=[
            _measurement_read(r, norms.get((r.source_id, r.substance))) for r in rows
        ],
        total=total,
    )


@router.post(
    "/emission-measurements",
    response_model=EmissionMeasurementRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_emission_measurement(
    request: Request,
    payload: EmissionMeasurementCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> EmissionMeasurementRead:
    """Внести замер. Строка плана необязательна — замер бывает внеплановым."""

    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_source_or_404(session, tenant, payload.source_id)
    plan_item = None
    if payload.plan_id:
        plan_item = await _get_plan_or_404(session, tenant, payload.plan_id)
    substance = payload.substance.strip()

    measurement = EmissionMeasurement(
        tenant_id=str(tenant.id),
        plan_id=payload.plan_id or None,
        source_id=payload.source_id,
        substance=substance,
        measured_on=payload.measured_on,
        value_grams_per_second=payload.value_grams_per_second,
        protocol_number=(payload.protocol_number or None),
        laboratory=(payload.laboratory or None),
        notes=(payload.notes or None),
    )
    session.add(measurement)
    # Внесение замера ДВИГАЕТ плановую дату вперёд по календарной сетке. Без
    # этого строка плана навсегда осталась бы просроченной: заводить данные
    # система умела бы, а исправлять уже заведённое — нет.
    if plan_item is not None:
        _advance_plan_due(plan_item, payload.measured_on)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="EmissionMeasurement",
        object_id=measurement.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": measurement.id}}},
        details={"entity": "EmissionMeasurement", "substance": measurement.substance},
    )
    await session.commit()
    await session.refresh(measurement)
    norm = await _norm_for_pair(session, tenant, measurement.source_id, substance)
    return _measurement_read(measurement, norm)


@router.patch(
    "/emission-measurements/{measurement_id}", response_model=EmissionMeasurementRead
)
async def update_emission_measurement(
    request: Request,
    measurement_id: str,
    payload: EmissionMeasurementUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> EmissionMeasurementRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    measurement = await _get_measurement_or_404(session, tenant, measurement_id)
    before = {
        "measured_on": str(measurement.measured_on),
        "value_grams_per_second": str(measurement.value_grams_per_second),
        "protocol_number": measurement.protocol_number,
        "laboratory": measurement.laboratory,
        "notes": measurement.notes,
    }
    data = payload.model_dump(exclude_unset=True)
    if data.get("measured_on") is not None:
        measurement.measured_on = data["measured_on"]
    if data.get("value_grams_per_second") is not None:
        measurement.value_grams_per_second = data["value_grams_per_second"]
    for field in ("protocol_number", "laboratory", "notes"):
        if field in data:
            setattr(measurement, field, data[field] or None)
    await session.flush()
    after = {
        "measured_on": str(measurement.measured_on),
        "value_grams_per_second": str(measurement.value_grams_per_second),
        "protocol_number": measurement.protocol_number,
        "laboratory": measurement.laboratory,
        "notes": measurement.notes,
    }
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="EmissionMeasurement",
        object_id=measurement.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "EmissionMeasurement"},
    )
    await session.commit()
    await session.refresh(measurement)
    norm = await _norm_for_pair(
        session, tenant, measurement.source_id, measurement.substance
    )
    return _measurement_read(measurement, norm)


# --- Водопользование: точки и помесячный учёт объёмов (разд. 55.2) ----------


def _permit_status(valid_until: date | None, today: date) -> str:
    """Состояние разрешения водопользования — считается ПРИ ЧТЕНИИ.

    Пустой срок — НЕ просрочка: забор из городского водопровода идёт по
    договору без срока, и объявлять такую точку нарушением было бы враньём.
    """

    return _norm_status(valid_until, today)


def _period_label(year: int, month: int) -> str:
    return f"{MONTH_TITLES.get(month, month)} {year}"


def _water_point_read(
    point: WaterUsagePoint, volume: Decimal, today: date
) -> WaterUsagePointRead:
    status_value = _permit_status(point.permit_valid_until, today)
    limit = point.annual_limit_cubic_meters
    return WaterUsagePointRead(
        id=point.id,
        facility_id=point.facility_id,
        point_number=point.point_number,
        name=point.name,
        kind=point.kind,
        kind_label=WATER_POINT_KINDS.get(point.kind, point.kind),
        water_body=point.water_body,
        permit_number=point.permit_number,
        permit_valid_until=point.permit_valid_until,
        annual_limit_cubic_meters=limit,
        notes=point.notes,
        permit_status=status_value,
        permit_status_label=WATER_PERMIT_STATUS_TITLES.get(status_value, status_value),
        volume_this_year=volume,
        # Без внесённого лимита превышения НЕ БЫВАЕТ: 999 999 м³ по точке без
        # лимита — это факт объёма, а не нарушение.
        over_limit=limit is not None and volume > limit,
    )


def _water_record_read(record: WaterUsageRecord) -> WaterUsageRecordRead:
    return WaterUsageRecordRead(
        id=record.id,
        point_id=record.point_id,
        period_year=record.period_year,
        period_month=record.period_month,
        period_label=_period_label(record.period_year, record.period_month),
        volume_cubic_meters=record.volume_cubic_meters,
        basis=record.basis,
        basis_label=WATER_RECORD_BASES.get(record.basis, record.basis),
        meter_number=record.meter_number,
        notes=record.notes,
    )


async def _water_volumes(
    session: AsyncSession, tenant: Tenant, point_ids: list[str], year: int
) -> dict[str, Decimal]:
    """Объём по каждой точке за год — одним запросом, а не N+1."""

    if not point_ids:
        return {}
    rows = await session.execute(
        select(WaterUsageRecord.point_id, func.sum(WaterUsageRecord.volume_cubic_meters))
        .where(
            WaterUsageRecord.tenant_id == tenant.id,
            WaterUsageRecord.deleted_at.is_(None),
            WaterUsageRecord.point_id.in_(point_ids),
            WaterUsageRecord.period_year == year,
        )
        .group_by(WaterUsageRecord.point_id)
    )
    return {row[0]: Decimal(str(row[1] or "0.000")) for row in rows}


async def _get_water_point_or_404(
    session: AsyncSession, tenant: Tenant, point_id: str
) -> WaterUsagePoint:
    stmt = select(WaterUsagePoint).where(
        WaterUsagePoint.id == point_id,
        WaterUsagePoint.tenant_id == tenant.id,
        WaterUsagePoint.deleted_at.is_(None),
    )
    point = (await session.execute(stmt)).scalar_one_or_none()
    if point is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="WATER_POINT_NOT_FOUND",
                message="Water usage point not found",
                error_type="ecology",
            ),
        )
    return point


async def _get_water_record_or_404(
    session: AsyncSession, tenant: Tenant, record_id: str
) -> WaterUsageRecord:
    stmt = select(WaterUsageRecord).where(
        WaterUsageRecord.id == record_id,
        WaterUsageRecord.tenant_id == tenant.id,
        WaterUsageRecord.deleted_at.is_(None),
    )
    record = (await session.execute(stmt)).scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="WATER_RECORD_NOT_FOUND",
                message="Water usage record not found",
                error_type="ecology",
            ),
        )
    return record


async def _ensure_point_number_free(
    session: AsyncSession,
    tenant: Tenant,
    facility_id: str,
    point_number: str,
    *,
    exclude_id: str | None = None,
) -> None:
    """Номер точки уникален В ПРЕДЕЛАХ ОБЪЕКТА — как номер источника выбросов."""

    stmt = select(WaterUsagePoint.id).where(
        WaterUsagePoint.tenant_id == tenant.id,
        WaterUsagePoint.facility_id == facility_id,
        WaterUsagePoint.point_number == point_number,
        WaterUsagePoint.deleted_at.is_(None),
    )
    if exclude_id:
        stmt = stmt.where(WaterUsagePoint.id != exclude_id)
    if (await session.execute(stmt)).scalar_one_or_none() is not None:
        raise _unprocessable(
            f"Точка с номером {point_number!r} на этом объекте уже заведена"
        )


async def _ensure_period_free(
    session: AsyncSession, tenant: Tenant, point_id: str, year: int, month: int
) -> None:
    """Учёт помесячный: две записи за один месяц по точке — ошибка ввода."""

    stmt = select(WaterUsageRecord.id).where(
        WaterUsageRecord.tenant_id == tenant.id,
        WaterUsageRecord.point_id == point_id,
        WaterUsageRecord.period_year == year,
        WaterUsageRecord.period_month == month,
        WaterUsageRecord.deleted_at.is_(None),
    )
    if (await session.execute(stmt)).scalar_one_or_none() is not None:
        raise _unprocessable(
            f"Учёт за {_period_label(year, month)} по этой точке уже внесён"
        )


@router.get("/water-points", response_model=WaterUsagePointPage)
async def list_water_points(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    facility_id: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> WaterUsagePointPage:
    """Точки водопользования: водозаборы и выпуски сточных вод."""

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(WaterUsagePoint).where(
        WaterUsagePoint.tenant_id == tenant.id,
        WaterUsagePoint.deleted_at.is_(None),
    )
    if facility_id:
        stmt = stmt.where(WaterUsagePoint.facility_id == facility_id)
    if kind:
        stmt = stmt.where(WaterUsagePoint.kind == kind)
    total = int(
        await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )
    rows = (
        (
            await session.execute(
                stmt.order_by(WaterUsagePoint.point_number).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    today = date.today()
    volumes = await _water_volumes(session, tenant, [r.id for r in rows], today.year)
    return WaterUsagePointPage(
        items=[
            _water_point_read(r, volumes.get(r.id, Decimal("0.000")), today)
            for r in rows
        ],
        total=total,
    )


@router.post(
    "/water-points",
    response_model=WaterUsagePointRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_water_point(
    request: Request,
    payload: WaterUsagePointCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> WaterUsagePointRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _validate_facility(session, tenant, payload.facility_id)
    if payload.kind not in WATER_POINT_KINDS:
        raise _unprocessable(
            f"Неизвестный тип точки {payload.kind!r}; допустимые: "
            f"{', '.join(WATER_POINT_KINDS)}"
        )
    point_number = payload.point_number.strip()
    await _ensure_point_number_free(
        session, tenant, payload.facility_id, point_number
    )

    point = WaterUsagePoint(
        tenant_id=str(tenant.id),
        facility_id=payload.facility_id,
        point_number=point_number,
        name=payload.name.strip(),
        kind=payload.kind,
        water_body=(payload.water_body or None),
        permit_number=(payload.permit_number or None),
        permit_valid_until=payload.permit_valid_until,
        annual_limit_cubic_meters=payload.annual_limit_cubic_meters,
        notes=(payload.notes or None),
    )
    session.add(point)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="WaterUsagePoint",
        object_id=point.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": point.id}}},
        details={"entity": "WaterUsagePoint", "point_number": point.point_number},
    )
    await session.commit()
    await session.refresh(point)
    return _water_point_read(point, Decimal("0.000"), date.today())


@router.patch("/water-points/{point_id}", response_model=WaterUsagePointRead)
async def update_water_point(
    request: Request,
    point_id: str,
    payload: WaterUsagePointUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> WaterUsagePointRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    point = await _get_water_point_or_404(session, tenant, point_id)
    before = {
        "point_number": point.point_number,
        "name": point.name,
        "kind": point.kind,
        "water_body": point.water_body,
        "permit_number": point.permit_number,
        "permit_valid_until": str(point.permit_valid_until),
        "annual_limit_cubic_meters": str(point.annual_limit_cubic_meters),
        "notes": point.notes,
    }
    data = payload.model_dump(exclude_unset=True)
    if data.get("kind"):
        if data["kind"] not in WATER_POINT_KINDS:
            raise _unprocessable(
                f"Неизвестный тип точки {data['kind']!r}; допустимые: "
                f"{', '.join(WATER_POINT_KINDS)}"
            )
        point.kind = str(data["kind"])
    if data.get("point_number"):
        number = str(data["point_number"]).strip()
        await _ensure_point_number_free(
            session, tenant, point.facility_id, number, exclude_id=point.id
        )
        point.point_number = number
    if data.get("name"):
        point.name = str(data["name"]).strip()
    if "permit_valid_until" in data:
        point.permit_valid_until = data["permit_valid_until"]
    if "annual_limit_cubic_meters" in data:
        point.annual_limit_cubic_meters = data["annual_limit_cubic_meters"]
    for field in ("water_body", "permit_number", "notes"):
        if field in data:
            setattr(point, field, data[field] or None)
    await session.flush()
    after = {
        "point_number": point.point_number,
        "name": point.name,
        "kind": point.kind,
        "water_body": point.water_body,
        "permit_number": point.permit_number,
        "permit_valid_until": str(point.permit_valid_until),
        "annual_limit_cubic_meters": str(point.annual_limit_cubic_meters),
        "notes": point.notes,
    }
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="WaterUsagePoint",
        object_id=point.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "WaterUsagePoint"},
    )
    await session.commit()
    await session.refresh(point)
    today = date.today()
    volumes = await _water_volumes(session, tenant, [point.id], today.year)
    return _water_point_read(point, volumes.get(point.id, Decimal("0.000")), today)


@router.get("/water-records", response_model=WaterUsageRecordPage)
async def list_water_records(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    point_id: str | None = Query(default=None),
    period_year: int | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> WaterUsageRecordPage:
    """Помесячный учёт объёмов по точкам водопользования."""

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(WaterUsageRecord).where(
        WaterUsageRecord.tenant_id == tenant.id,
        WaterUsageRecord.deleted_at.is_(None),
    )
    if point_id:
        stmt = stmt.where(WaterUsageRecord.point_id == point_id)
    if period_year:
        stmt = stmt.where(WaterUsageRecord.period_year == period_year)
    total = int(
        await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )
    rows = (
        (
            await session.execute(
                stmt.order_by(
                    WaterUsageRecord.period_year.desc(),
                    WaterUsageRecord.period_month.desc(),
                )
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return WaterUsageRecordPage(
        items=[_water_record_read(r) for r in rows], total=total
    )


@router.post(
    "/water-records",
    response_model=WaterUsageRecordRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_water_record(
    request: Request,
    payload: WaterUsageRecordCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> WaterUsageRecordRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_water_point_or_404(session, tenant, payload.point_id)
    if payload.basis not in WATER_RECORD_BASES:
        raise _unprocessable(
            f"Неизвестное основание учёта {payload.basis!r}; допустимые: "
            f"{', '.join(WATER_RECORD_BASES)}"
        )
    await _ensure_period_free(
        session, tenant, payload.point_id, payload.period_year, payload.period_month
    )

    record = WaterUsageRecord(
        tenant_id=str(tenant.id),
        point_id=payload.point_id,
        period_year=payload.period_year,
        period_month=payload.period_month,
        volume_cubic_meters=payload.volume_cubic_meters,
        basis=payload.basis,
        meter_number=(payload.meter_number or None),
        notes=(payload.notes or None),
    )
    session.add(record)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="WaterUsageRecord",
        object_id=record.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": record.id}}},
        details={
            "entity": "WaterUsageRecord",
            "period": _period_label(record.period_year, record.period_month),
        },
    )
    await session.commit()
    await session.refresh(record)
    return _water_record_read(record)


@router.patch("/water-records/{record_id}", response_model=WaterUsageRecordRead)
async def update_water_record(
    request: Request,
    record_id: str,
    payload: WaterUsageRecordUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> WaterUsageRecordRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    record = await _get_water_record_or_404(session, tenant, record_id)
    before = {
        "volume_cubic_meters": str(record.volume_cubic_meters),
        "basis": record.basis,
        "meter_number": record.meter_number,
        "notes": record.notes,
    }
    data = payload.model_dump(exclude_unset=True)
    if data.get("basis"):
        if data["basis"] not in WATER_RECORD_BASES:
            raise _unprocessable(
                f"Неизвестное основание учёта {data['basis']!r}; допустимые: "
                f"{', '.join(WATER_RECORD_BASES)}"
            )
        record.basis = str(data["basis"])
    if data.get("volume_cubic_meters") is not None:
        record.volume_cubic_meters = data["volume_cubic_meters"]
    for field in ("meter_number", "notes"):
        if field in data:
            setattr(record, field, data[field] or None)
    await session.flush()
    after = {
        "volume_cubic_meters": str(record.volume_cubic_meters),
        "basis": record.basis,
        "meter_number": record.meter_number,
        "notes": record.notes,
    }
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="WaterUsageRecord",
        object_id=record.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "WaterUsageRecord"},
    )
    await session.commit()
    await session.refresh(record)
    return _water_record_read(record)


# --- Плата за НВОС: справочник ставок и строки расчёта (разд. 55.3) ---------

#: рубли считаем до копеек — это денежная сумма, а не приблизительная оценка
_KOPECKS = Decimal("0.01")


def _rate_read(rate: NvosFeeRate) -> NvosFeeRateRead:
    return NvosFeeRateRead(
        id=rate.id,
        year=rate.year,
        impact_kind=rate.impact_kind,
        impact_kind_label=FEE_IMPACT_KINDS.get(rate.impact_kind, rate.impact_kind),
        subject=rate.subject,
        rate_per_ton=rate.rate_per_ton,
        source_document=rate.source_document,
        notes=rate.notes,
    )


def _fee_line_read(line: NvosFeeLine, rate: NvosFeeRate | None) -> NvosFeeLineRead:
    """Строка расчёта вместе с суммой.

    Нет ставки — сумма НЕ СЧИТАЕТСЯ ВООБЩЕ, а не считается нулём: ноль читался
    бы как «платить нечего», и это было бы враньём. Тот же довод, что и у
    «норматив не внесён» в замерах ПЭК.
    """

    status_value = "found" if rate is not None else "missing"
    amount = (
        (line.mass_tons * rate.rate_per_ton * line.coefficient).quantize(_KOPECKS)
        if rate is not None
        else None
    )
    return NvosFeeLineRead(
        id=line.id,
        year=line.year,
        quarter=line.quarter,
        impact_kind=line.impact_kind,
        impact_kind_label=FEE_IMPACT_KINDS.get(line.impact_kind, line.impact_kind),
        subject=line.subject,
        mass_tons=line.mass_tons,
        coefficient=line.coefficient,
        notes=line.notes,
        rate_status=status_value,
        rate_status_label=FEE_RATE_STATUS_TITLES.get(status_value, status_value),
        rate_per_ton=rate.rate_per_ton if rate is not None else None,
        amount_rubles=amount,
    )


async def _rates_by_key(
    session: AsyncSession, tenant: Tenant
) -> dict[tuple[int, str, str], NvosFeeRate]:
    """Ставки по ключу «год + вид + предмет» — одним запросом, а не N+1.

    Год входит в ключ НАМЕРЕННО: расчёт за этот год не имеет права взять
    прошлогоднюю ставку — это разные постановления.
    """

    rows = (
        (
            await session.execute(
                select(NvosFeeRate).where(
                    NvosFeeRate.tenant_id == tenant.id,
                    NvosFeeRate.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    return {(r.year, r.impact_kind, r.subject): r for r in rows}


async def _get_rate_or_404(
    session: AsyncSession, tenant: Tenant, rate_id: str
) -> NvosFeeRate:
    stmt = select(NvosFeeRate).where(
        NvosFeeRate.id == rate_id,
        NvosFeeRate.tenant_id == tenant.id,
        NvosFeeRate.deleted_at.is_(None),
    )
    rate = (await session.execute(stmt)).scalar_one_or_none()
    if rate is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="NVOS_FEE_RATE_NOT_FOUND",
                message="Fee rate not found",
                error_type="ecology",
            ),
        )
    return rate


async def _get_fee_line_or_404(
    session: AsyncSession, tenant: Tenant, line_id: str
) -> NvosFeeLine:
    stmt = select(NvosFeeLine).where(
        NvosFeeLine.id == line_id,
        NvosFeeLine.tenant_id == tenant.id,
        NvosFeeLine.deleted_at.is_(None),
    )
    line = (await session.execute(stmt)).scalar_one_or_none()
    if line is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="NVOS_FEE_LINE_NOT_FOUND",
                message="Fee line not found",
                error_type="ecology",
            ),
        )
    return line


def _validate_impact_kind(value: str) -> None:
    if value not in FEE_IMPACT_KINDS:
        raise _unprocessable(
            f"Неизвестный вид воздействия {value!r}; допустимые: "
            f"{', '.join(FEE_IMPACT_KINDS)}"
        )


@router.get("/fee-rates", response_model=NvosFeeRatePage)
async def list_fee_rates(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    year: int | None = Query(default=None),
    impact_kind: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> NvosFeeRatePage:
    """Справочник ставок платы за НВОС по годам."""

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(NvosFeeRate).where(
        NvosFeeRate.tenant_id == tenant.id,
        NvosFeeRate.deleted_at.is_(None),
    )
    if year:
        stmt = stmt.where(NvosFeeRate.year == year)
    if impact_kind:
        stmt = stmt.where(NvosFeeRate.impact_kind == impact_kind)
    total = int(
        await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )
    rows = (
        (
            await session.execute(
                stmt.order_by(NvosFeeRate.year.desc(), NvosFeeRate.subject)
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return NvosFeeRatePage(items=[_rate_read(r) for r in rows], total=total)


@router.post(
    "/fee-rates", response_model=NvosFeeRateRead, status_code=status.HTTP_201_CREATED
)
async def create_fee_rate(
    request: Request,
    payload: NvosFeeRateCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> NvosFeeRateRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _validate_impact_kind(payload.impact_kind)
    subject = payload.subject.strip()
    existing = await session.execute(
        select(NvosFeeRate.id).where(
            NvosFeeRate.tenant_id == tenant.id,
            NvosFeeRate.year == payload.year,
            NvosFeeRate.impact_kind == payload.impact_kind,
            NvosFeeRate.subject == subject,
            NvosFeeRate.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise _unprocessable(
            f"Ставка на {payload.year} год по {subject!r} уже внесена"
        )

    rate = NvosFeeRate(
        tenant_id=str(tenant.id),
        year=payload.year,
        impact_kind=payload.impact_kind,
        subject=subject,
        rate_per_ton=payload.rate_per_ton,
        source_document=(payload.source_document or None),
        notes=(payload.notes or None),
    )
    session.add(rate)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="NvosFeeRate",
        object_id=rate.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": rate.id}}},
        details={"entity": "NvosFeeRate", "subject": rate.subject},
    )
    await session.commit()
    await session.refresh(rate)
    return _rate_read(rate)


@router.patch("/fee-rates/{rate_id}", response_model=NvosFeeRateRead)
async def update_fee_rate(
    request: Request,
    rate_id: str,
    payload: NvosFeeRateUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> NvosFeeRateRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    rate = await _get_rate_or_404(session, tenant, rate_id)
    before = {
        "rate_per_ton": str(rate.rate_per_ton),
        "source_document": rate.source_document,
        "notes": rate.notes,
    }
    data = payload.model_dump(exclude_unset=True)
    if data.get("rate_per_ton") is not None:
        rate.rate_per_ton = data["rate_per_ton"]
    for field in ("source_document", "notes"):
        if field in data:
            setattr(rate, field, data[field] or None)
    await session.flush()
    after = {
        "rate_per_ton": str(rate.rate_per_ton),
        "source_document": rate.source_document,
        "notes": rate.notes,
    }
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="NvosFeeRate",
        object_id=rate.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "NvosFeeRate"},
    )
    await session.commit()
    await session.refresh(rate)
    return _rate_read(rate)


@router.get("/fee-lines", response_model=NvosFeeLinePage)
async def list_fee_lines(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    year: int | None = Query(default=None),
    quarter: int | None = Query(default=None, ge=1, le=4),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> NvosFeeLinePage:
    """Строки расчёта платы: кварталы — это и есть авансовые платежи."""

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(NvosFeeLine).where(
        NvosFeeLine.tenant_id == tenant.id,
        NvosFeeLine.deleted_at.is_(None),
    )
    if year:
        stmt = stmt.where(NvosFeeLine.year == year)
    if quarter:
        stmt = stmt.where(NvosFeeLine.quarter == quarter)
    total = int(
        await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )
    rows = (
        (
            await session.execute(
                stmt.order_by(
                    NvosFeeLine.year.desc(), NvosFeeLine.quarter, NvosFeeLine.subject
                )
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    rates = await _rates_by_key(session, tenant)
    return NvosFeeLinePage(
        items=[
            _fee_line_read(r, rates.get((r.year, r.impact_kind, r.subject)))
            for r in rows
        ],
        total=total,
    )


@router.post(
    "/fee-lines", response_model=NvosFeeLineRead, status_code=status.HTTP_201_CREATED
)
async def create_fee_line(
    request: Request,
    payload: NvosFeeLineCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> NvosFeeLineRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _validate_impact_kind(payload.impact_kind)
    subject = payload.subject.strip()
    existing = await session.execute(
        select(NvosFeeLine.id).where(
            NvosFeeLine.tenant_id == tenant.id,
            NvosFeeLine.year == payload.year,
            NvosFeeLine.quarter == payload.quarter,
            NvosFeeLine.impact_kind == payload.impact_kind,
            NvosFeeLine.subject == subject,
            NvosFeeLine.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise _unprocessable(
            f"Строка расчёта за {payload.quarter} квартал {payload.year} года "
            f"по {subject!r} уже внесена"
        )

    line = NvosFeeLine(
        tenant_id=str(tenant.id),
        year=payload.year,
        quarter=payload.quarter,
        impact_kind=payload.impact_kind,
        subject=subject,
        mass_tons=payload.mass_tons,
        coefficient=payload.coefficient,
        notes=(payload.notes or None),
    )
    session.add(line)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="NvosFeeLine",
        object_id=line.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": line.id}}},
        details={"entity": "NvosFeeLine", "subject": line.subject},
    )
    await session.commit()
    await session.refresh(line)
    rates = await _rates_by_key(session, tenant)
    return _fee_line_read(line, rates.get((line.year, line.impact_kind, line.subject)))


@router.patch("/fee-lines/{line_id}", response_model=NvosFeeLineRead)
async def update_fee_line(
    request: Request,
    line_id: str,
    payload: NvosFeeLineUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> NvosFeeLineRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    line = await _get_fee_line_or_404(session, tenant, line_id)
    before = {
        "mass_tons": str(line.mass_tons),
        "coefficient": str(line.coefficient),
        "notes": line.notes,
    }
    data = payload.model_dump(exclude_unset=True)
    if data.get("mass_tons") is not None:
        line.mass_tons = data["mass_tons"]
    if data.get("coefficient") is not None:
        line.coefficient = data["coefficient"]
    if "notes" in data:
        line.notes = data["notes"] or None
    await session.flush()
    after = {
        "mass_tons": str(line.mass_tons),
        "coefficient": str(line.coefficient),
        "notes": line.notes,
    }
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="NvosFeeLine",
        object_id=line.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "NvosFeeLine"},
    )
    await session.commit()
    await session.refresh(line)
    rates = await _rates_by_key(session, tenant)
    return _fee_line_read(line, rates.get((line.year, line.impact_kind, line.subject)))


# ── Сроки отчётности и платежей (разд. 55.3, разд. 57.2; срез-71) ────────────


def reporting_status(due_on: date, done_on: date | None, today: date) -> str:
    """planned / overdue / done — одна формула у реестра, сводки и календаря.

    Исполненный срок просроченным не бывает, даже если сдали позже даты:
    просрочка — это то, что ещё требует действия.
    """

    if done_on is not None:
        return "done"
    return "overdue" if due_on < today else "planned"


def _reporting_read(row: EcologyReportingDeadline) -> EcologyReportingDeadlineRead:
    status_value = reporting_status(row.due_on, row.done_on, date.today())
    return EcologyReportingDeadlineRead(
        id=row.id,
        kind=row.kind,
        kind_label=REPORTING_KINDS.get(row.kind, row.kind),
        title=row.title,
        period=row.period,
        due_on=row.due_on,
        done_on=row.done_on,
        responsible=row.responsible,
        notes=row.notes,
        status=status_value,
        status_label=REPORTING_STATUS_TITLES[status_value],
    )


def _validate_reporting_kind(value: str) -> None:
    if value not in REPORTING_KINDS:
        raise _unprocessable(
            f"Неизвестный вид срока {value!r}; допустимые: {', '.join(REPORTING_KINDS)}"
        )


async def _ensure_reporting_deadline_free(
    session: AsyncSession,
    tenant: Tenant,
    *,
    title: str,
    due_on: date,
    exclude_id: str | None = None,
) -> None:
    """Один и тот же отчёт на одну дату — один срок: дубль дал бы две строки
    в Центре внимания и удвоил бы «просрочено» в сводке."""

    stmt = select(EcologyReportingDeadline.id).where(
        EcologyReportingDeadline.tenant_id == tenant.id,
        EcologyReportingDeadline.title == title,
        EcologyReportingDeadline.due_on == due_on,
        EcologyReportingDeadline.deleted_at.is_(None),
    )
    if exclude_id:
        stmt = stmt.where(EcologyReportingDeadline.id != exclude_id)
    if (await session.execute(stmt)).scalar_one_or_none() is not None:
        raise _unprocessable(f"Срок {title!r} на {due_on.isoformat()} уже внесён")


async def _get_reporting_deadline_or_404(
    session: AsyncSession, tenant: Tenant, deadline_id: str
) -> EcologyReportingDeadline:
    stmt = select(EcologyReportingDeadline).where(
        EcologyReportingDeadline.id == deadline_id,
        EcologyReportingDeadline.tenant_id == tenant.id,
        EcologyReportingDeadline.deleted_at.is_(None),
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="NVOS_REPORTING_DEADLINE_NOT_FOUND",
                message="Reporting deadline not found",
                error_type="ecology",
            ),
        )
    return row


@router.get("/reporting-deadlines", response_model=EcologyReportingDeadlinePage)
async def list_reporting_deadlines(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    kind: str | None = Query(default=None),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="planned / overdue / done; пусто — все",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> EcologyReportingDeadlinePage:
    """Сроки сдачи отчётности и платежей: ближайшие сверху, исполненные — тоже
    (ради истории), но их отличает состояние."""

    TenantContextValidator.ensure_tenant_context(tenant)
    if kind is not None:
        _validate_reporting_kind(kind)
    if status_filter is not None and status_filter not in REPORTING_STATUS_TITLES:
        raise _unprocessable(
            f"Неизвестное состояние {status_filter!r}; допустимые: "
            f"{', '.join(REPORTING_STATUS_TITLES)}"
        )
    today = date.today()
    stmt = select(EcologyReportingDeadline).where(
        EcologyReportingDeadline.tenant_id == tenant.id,
        EcologyReportingDeadline.deleted_at.is_(None),
    )
    if kind:
        stmt = stmt.where(EcologyReportingDeadline.kind == kind)
    if status_filter == "done":
        stmt = stmt.where(EcologyReportingDeadline.done_on.is_not(None))
    elif status_filter == "overdue":
        stmt = stmt.where(
            EcologyReportingDeadline.done_on.is_(None),
            EcologyReportingDeadline.due_on < today,
        )
    elif status_filter == "planned":
        stmt = stmt.where(
            EcologyReportingDeadline.done_on.is_(None),
            EcologyReportingDeadline.due_on >= today,
        )
    total = int(
        await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )
    rows = (
        (
            await session.execute(
                stmt.order_by(
                    EcologyReportingDeadline.due_on.asc(), EcologyReportingDeadline.title
                )
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return EcologyReportingDeadlinePage(
        items=[_reporting_read(r) for r in rows], total=total
    )


@router.post(
    "/reporting-deadlines",
    response_model=EcologyReportingDeadlineRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_reporting_deadline(
    request: Request,
    payload: EcologyReportingDeadlineCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> EcologyReportingDeadlineRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _validate_reporting_kind(payload.kind)
    title = payload.title.strip()
    if not title:
        raise _unprocessable("Название срока не может быть пустым")
    await _ensure_reporting_deadline_free(
        session, tenant, title=title, due_on=payload.due_on
    )

    row = EcologyReportingDeadline(
        tenant_id=str(tenant.id),
        kind=payload.kind,
        title=title,
        period=(payload.period or None),
        due_on=payload.due_on,
        done_on=payload.done_on,
        responsible=(payload.responsible or None),
        notes=(payload.notes or None),
    )
    session.add(row)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="EcologyReportingDeadline",
        object_id=row.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": row.id}}},
        details={"entity": "EcologyReportingDeadline", "title": row.title},
    )
    await session.commit()
    await session.refresh(row)
    return _reporting_read(row)


@router.patch(
    "/reporting-deadlines/{deadline_id}", response_model=EcologyReportingDeadlineRead
)
async def update_reporting_deadline(
    request: Request,
    deadline_id: str,
    payload: EcologyReportingDeadlineUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> EcologyReportingDeadlineRead:
    """Правка срока; ``done_on`` — отметка «сдано/уплачено», ``null`` её снимает."""

    TenantContextValidator.ensure_tenant_context(tenant)
    row = await _get_reporting_deadline_or_404(session, tenant, deadline_id)
    fields = ("title", "period", "due_on", "done_on", "responsible", "notes")
    before = {f: (v.isoformat() if isinstance(v := getattr(row, f), date) else v) for f in fields}
    data = payload.model_dump(exclude_unset=True)
    if "title" in data and data["title"] is not None:
        row.title = data["title"].strip() or row.title
    if data.get("due_on") is not None:
        row.due_on = data["due_on"]
    if "title" in data or "due_on" in data:
        await _ensure_reporting_deadline_free(
            session, tenant, title=row.title, due_on=row.due_on, exclude_id=row.id
        )
    if "done_on" in data:
        row.done_on = data["done_on"]
    for field in ("period", "responsible", "notes"):
        if field in data:
            setattr(row, field, data[field] or None)
    await session.flush()
    after = {f: (v.isoformat() if isinstance(v := getattr(row, f), date) else v) for f in fields}
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="EcologyReportingDeadline",
        object_id=row.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "EcologyReportingDeadline"},
    )
    await session.commit()
    await session.refresh(row)
    return _reporting_read(row)


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
    # Разд. 55.2 «отходы»: паспорта, записи журнала и превышения лимита.
    year = date.today().year
    passports = (
        (
            await session.execute(
                select(WastePassport).where(
                    WastePassport.tenant_id == tenant.id,
                    WastePassport.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    generated = await _generated_this_year(
        session, tenant, [p.id for p in passports], year
    )
    movements_total = int(
        await session.scalar(
            select(func.count())
            .select_from(WasteMovement)
            .where(
                WasteMovement.tenant_id == tenant.id,
                WasteMovement.deleted_at.is_(None),
            )
        )
        or 0
    )
    over_limit = sum(
        1
        for p in passports
        if p.annual_limit_tons is not None
        and generated.get(p.id, Decimal("0.000")) > p.annual_limit_tons
    )

    # Разд. 55.2 «выбросы»: инвентаризация и нормативы.
    sources = (
        (
            await session.execute(
                select(EmissionSource).where(
                    EmissionSource.tenant_id == tenant.id,
                    EmissionSource.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    norms = (
        (
            await session.execute(
                select(EmissionNorm).where(
                    EmissionNorm.tenant_id == tenant.id,
                    EmissionNorm.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    sources_with_norms = {n.source_id for n in norms}
    today = date.today()
    permits_overdue = sum(
        1 for n in norms if _norm_status(n.valid_until, today) == "overdue"
    )

    # Разд. 55.2 «ПЭК»: график, просрочки и превышения по ЗАМЕРАМ. Превышение
    # здесь — сравнение двух внесённых чисел, а не вывод платформы о нормативе.
    plan_items = (
        (
            await session.execute(
                select(EmissionMonitoringPlanItem).where(
                    EmissionMonitoringPlanItem.tenant_id == tenant.id,
                    EmissionMonitoringPlanItem.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    measurements = (
        (
            await session.execute(
                select(EmissionMeasurement).where(
                    EmissionMeasurement.tenant_id == tenant.id,
                    EmissionMeasurement.deleted_at.is_(None),
                    EmissionMeasurement.measured_on >= date(year, 1, 1),
                )
            )
        )
        .scalars()
        .all()
    )
    norm_by_pair = {(n.source_id, n.substance): n for n in norms}
    exceeded = sum(
        1
        for m in measurements
        if _comparison(
            m.value_grams_per_second, norm_by_pair.get((m.source_id, m.substance))
        )[0]
        == "exceeded"
    )

    # Разд. 55.2 «водопользование»: точки, разрешения и объёмы за год. Забор и
    # сброс считаются РАЗДЕЛЬНО — это разные величины.
    water_points = (
        (
            await session.execute(
                select(WaterUsagePoint).where(
                    WaterUsagePoint.tenant_id == tenant.id,
                    WaterUsagePoint.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    water_volumes = await _water_volumes(
        session, tenant, [p.id for p in water_points], year
    )
    intake = sum(
        (
            water_volumes.get(p.id, Decimal("0.000"))
            for p in water_points
            if p.kind == "intake"
        ),
        Decimal("0.000"),
    )
    discharge = sum(
        (
            water_volumes.get(p.id, Decimal("0.000"))
            for p in water_points
            if p.kind == "discharge"
        ),
        Decimal("0.000"),
    )

    # Разд. 55.3 «плата за НВОС» за текущий год. В итог попадает только то,
    # что посчитано: строка без ставки НЕ прибавляет ноль, иначе итог выглядел
    # бы полным.
    fee_lines = (
        (
            await session.execute(
                select(NvosFeeLine).where(
                    NvosFeeLine.tenant_id == tenant.id,
                    NvosFeeLine.deleted_at.is_(None),
                    NvosFeeLine.year == year,
                )
            )
        )
        .scalars()
        .all()
    )
    fee_rates = await _rates_by_key(session, tenant)
    fee_total = Decimal("0.00")
    fee_without_rate = 0
    for line in fee_lines:
        rate = fee_rates.get((line.year, line.impact_kind, line.subject))
        if rate is None:
            fee_without_rate += 1
            continue
        fee_total += (line.mass_tons * rate.rate_per_ton * line.coefficient).quantize(
            _KOPECKS
        )

    # Разд. 55.3 «сроки сдачи отчётности, платежей» (срез-71): просрочено —
    # не исполнено и дата прошла; исполненное с опозданием просрочкой не
    # считается (та же формула, что у реестра и календаря).
    reporting_overdue = int(
        await session.scalar(
            select(func.count())
            .select_from(EcologyReportingDeadline)
            .where(
                EcologyReportingDeadline.tenant_id == tenant.id,
                EcologyReportingDeadline.deleted_at.is_(None),
                EcologyReportingDeadline.done_on.is_(None),
                EcologyReportingDeadline.due_on < today,
            )
        )
        or 0
    )

    return EcologyReadinessRead(
        reporting_overdue=reporting_overdue,
        fee_lines=len(fee_lines),
        fee_lines_without_rate=fee_without_rate,
        fee_total_rubles=fee_total,
        water_points=len(water_points),
        water_permits_overdue=sum(
            1
            for p in water_points
            if _permit_status(p.permit_valid_until, today) == "overdue"
        ),
        water_intake_cubic_meters=intake,
        water_discharge_cubic_meters=discharge,
        # Превышение — ФАКТ по внесённому лимиту: без лимита его не бывает.
        water_over_limit=sum(
            1
            for p in water_points
            if p.annual_limit_cubic_meters is not None
            and water_volumes.get(p.id, Decimal("0.000")) > p.annual_limit_cubic_meters
        ),
        monitoring_plan_items=len(plan_items),
        monitoring_overdue=sum(
            1
            for i in plan_items
            if _monitoring_status(i.next_due_on, today) == "overdue"
        ),
        measurements_this_year=len(measurements),
        measurements_exceeded=exceeded,
        emission_sources=len(sources),
        emission_sources_without_norms=sum(
            1 for s in sources if s.id not in sources_with_norms
        ),
        emission_norms=len(norms),
        emission_permits_overdue=permits_overdue,
        waste_passports=len(passports),
        waste_movements=movements_total,
        waste_over_limit=over_limit,
        total_facilities=len(active),
        by_category=by_category,
        excluded_facilities=len(rows) - len(active),
        # ФАКТ, а не нарушение: обязанность актуализировать сведения возникает
        # при изменении характеристик объекта, а не по календарю.
        never_actualized=sum(1 for r in active if r.actualized_on is None),
        # Доп. №1 разд. 57.4: открытые происшествия контура — той же формулой,
        # что разрез «по дисциплинам» у директора (срез-49).
        incidents_open=await open_incidents_count(session, str(tenant.id), Discipline.ECOLOGY),
    )
