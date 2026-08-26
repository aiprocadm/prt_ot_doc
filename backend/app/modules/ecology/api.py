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

from datetime import date
from decimal import Decimal
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
    WASTE_HAZARD_CLASSES,
    WASTE_MOVEMENT_KINDS,
    EnvironmentalFacility,
    WasteMovement,
    WastePassport,
)
from app.models.finance import Contract
from app.models.master_data import Site
from app.models.models import Tenant
from app.schemas.ecology import (
    EcologyReadinessRead,
    EnvironmentalFacilityCreate,
    EnvironmentalFacilityPage,
    EnvironmentalFacilityRead,
    EnvironmentalFacilityUpdate,
    WasteMovementCreate,
    WasteMovementPage,
    WasteMovementRead,
    WasteMovementUpdate,
    WastePassportCreate,
    WastePassportPage,
    WastePassportRead,
    WastePassportUpdate,
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

    return EcologyReadinessRead(
        waste_passports=len(passports),
        waste_movements=movements_total,
        waste_over_limit=over_limit,
        total_facilities=len(active),
        by_category=by_category,
        excluded_facilities=len(rows) - len(active),
        # ФАКТ, а не нарушение: обязанность актуализировать сведения возникает
        # при изменении характеристик объекта, а не по календарю.
        never_actualized=sum(1 for r in active if r.actualized_on is None),
    )
