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

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.disciplines import (
    ATTESTATION_AREA_TITLES,
    Discipline,
    areas_of_discipline,
    discipline_write_roles,
)
from app.core.errors import api_problem_detail
from app.core.feature_flags import is_module_enabled, raise_for_disabled_module
from app.core.security import AccessContext, abac, rbac
from app.core.tenant_validation import TenantContextValidator
from app.models.industrial_safety import (
    OPO_ATTESTATION_STATUS_TITLES,
    OPO_DEVICE_KINDS,
    OPO_DEVICE_STATUSES,
    OPO_EPB_STATUS_TITLES,
    OPO_HAZARD_CLASSES,
    OPO_STATUSES,
    OPO_WORK_KIND_EXTENDING_EPB,
    OPO_WORK_KINDS,
    OPO_WORK_PASSING_RESULTS,
    OPO_WORK_RESULTS,
    PC_MEASURE_SECTIONS,
    PC_MEASURE_STATUS_TITLES,
    PC_MEASURE_WRITABLE_STATUSES,
    PC_PLAN_STATUSES,
    DeviceWorkRecord,
    HazardousFacility,
    ProductionControlMeasure,
    ProductionControlPlan,
    TechnicalDevice,
)
from app.models.master_data import Person, Site
from app.models.models import Attestation, Tenant
from app.schemas.industrial_safety import (
    DeviceWorkCreate,
    DeviceWorkPage,
    DeviceWorkRead,
    HazardousFacilityCreate,
    HazardousFacilityPage,
    HazardousFacilityRead,
    HazardousFacilityUpdate,
    IndustrialReadinessRead,
    OpoAttestationPage,
    OpoAttestationRead,
    PcMeasureCreate,
    PcMeasurePage,
    PcMeasureRead,
    PcMeasureUpdate,
    PcPlanCreate,
    PcPlanPage,
    PcPlanRead,
    PcPlanUpdate,
    TechnicalDeviceCreate,
    TechnicalDevicePage,
    TechnicalDeviceRead,
    TechnicalDeviceUpdate,
)
from app.services.audit import AuditService, field_level_diff
from app.services.discipline_incidents import open_incidents_count

router = APIRouter(prefix="/industrial-safety", tags=["industrial-safety"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

#: Право на запись у контура — общее для всех дисциплин (срез-119):
#: один список в ядре вместо пяти одинаковых копий по модулям.
_ROLES = list(discipline_write_roles(Discipline.INDUSTRIAL_SAFETY))


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


#: горизонт «скоро истекает» — тот же, что у остальной готовности к проверке
_DUE_SOON_DAYS = 30


def _epb_status(device: TechnicalDevice, today: date) -> str:
    """Состояние заключения ЭПБ — считается ПРИ ЧТЕНИИ.

    «Заключения нет» — ОТДЕЛЬНОЕ состояние, а не разновидность просрочки:
    слить их значило бы либо обвинить исправное новое устройство, либо
    спрятать то, что отработало назначенный срок службы без экспертизы.
    """

    if device.epb_valid_until is None:
        return "absent"
    if device.epb_valid_until < today:
        return "overdue"
    if device.epb_valid_until <= today + timedelta(days=_DUE_SOON_DAYS):
        return "due_soon"
    return "ok"


def _device_read(
    device: TechnicalDevice,
    today: date,
    last_work: tuple[date, str] | None = None,
) -> TechnicalDeviceRead:
    epb = _epb_status(device, today)
    return TechnicalDeviceRead(
        id=device.id,
        facility_id=device.facility_id,
        kind=device.kind,
        kind_label=OPO_DEVICE_KINDS.get(device.kind, device.kind),
        name=device.name,
        serial_number=device.serial_number,
        commissioned_on=device.commissioned_on,
        lifetime_until=device.lifetime_until,
        epb_conclusion_number=device.epb_conclusion_number,
        epb_registered_on=device.epb_registered_on,
        epb_valid_until=device.epb_valid_until,
        status=device.status,
        status_label=OPO_DEVICE_STATUSES.get(device.status, device.status),
        notes=device.notes,
        epb_status=epb,
        epb_status_label=OPO_EPB_STATUS_TITLES.get(epb, epb),
        past_lifetime=(
            device.lifetime_until is not None and device.lifetime_until < today
        ),
        last_work_on=last_work[0] if last_work else None,
        last_work_result=last_work[1] if last_work else None,
    )


async def _validate_facility(
    session: AsyncSession, tenant: Tenant, facility_id: str | None
) -> None:
    if not facility_id:
        return
    stmt = select(HazardousFacility.id).where(
        HazardousFacility.id == facility_id,
        HazardousFacility.tenant_id == tenant.id,
        HazardousFacility.deleted_at.is_(None),
    )
    if (await session.execute(stmt)).scalar_one_or_none() is None:
        raise _unprocessable("Объект не найден")


def _validate_device_dictionaries(
    *, kind: str | None, status_value: str | None
) -> None:
    if kind is not None and kind not in OPO_DEVICE_KINDS:
        raise _unprocessable(
            f"Неизвестный тип устройства {kind!r}; допустимые: "
            f"{', '.join(OPO_DEVICE_KINDS)}"
        )
    if status_value is not None and status_value not in OPO_DEVICE_STATUSES:
        raise _unprocessable(
            f"Неизвестное состояние {status_value!r}; допустимые: "
            f"{', '.join(OPO_DEVICE_STATUSES)}"
        )


async def _get_device_or_404(
    session: AsyncSession, tenant: Tenant, device_id: str
) -> TechnicalDevice:
    stmt = select(TechnicalDevice).where(
        TechnicalDevice.id == device_id,
        TechnicalDevice.tenant_id == tenant.id,
        TechnicalDevice.deleted_at.is_(None),
    )
    device = (await session.execute(stmt)).scalar_one_or_none()
    if device is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="TECHNICAL_DEVICE_NOT_FOUND",
                message="Technical device not found",
                error_type="industrial_safety",
            ),
        )
    return device


@router.get("/devices", response_model=TechnicalDevicePage)
async def list_devices(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    facility_id: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TechnicalDevicePage:
    """Что эксплуатируется на объекте и в каком состоянии его экспертиза."""

    TenantContextValidator.ensure_tenant_context(tenant)
    today = date.today()
    stmt = select(TechnicalDevice).where(
        TechnicalDevice.tenant_id == tenant.id,
        TechnicalDevice.deleted_at.is_(None),
    )
    if facility_id:
        stmt = stmt.where(TechnicalDevice.facility_id == facility_id)
    if kind:
        stmt = stmt.where(TechnicalDevice.kind == kind)
    if status_filter:
        stmt = stmt.where(TechnicalDevice.status == status_filter)
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        (
            await session.execute(
                stmt.order_by(TechnicalDevice.name).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    last_works = await _last_work_map(session, tenant, [r.id for r in rows])
    return TechnicalDevicePage(
        items=[_device_read(r, today, last_works.get(r.id)) for r in rows],
        total=total,
    )


@router.post(
    "/devices", response_model=TechnicalDeviceRead, status_code=status.HTTP_201_CREATED
)
async def create_device(
    request: Request,
    payload: TechnicalDeviceCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> TechnicalDeviceRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _validate_facility(session, tenant, payload.facility_id)
    _validate_device_dictionaries(kind=payload.kind, status_value=payload.status)

    device = TechnicalDevice(
        tenant_id=str(tenant.id),
        facility_id=payload.facility_id,
        kind=payload.kind,
        name=payload.name.strip(),
        serial_number=(payload.serial_number or None),
        commissioned_on=payload.commissioned_on,
        lifetime_until=payload.lifetime_until,
        epb_conclusion_number=(payload.epb_conclusion_number or None),
        epb_registered_on=payload.epb_registered_on,
        epb_valid_until=payload.epb_valid_until,
        status=payload.status or "in_operation",
        notes=(payload.notes or None),
    )
    session.add(device)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="TechnicalDevice",
        object_id=device.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": device.id}}},
        details={
            "entity": "TechnicalDevice",
            "kind": device.kind,
            "facility_id": device.facility_id,
        },
    )
    await session.commit()
    await session.refresh(device)
    return _device_read(device, date.today())


@router.patch("/devices/{device_id}", response_model=TechnicalDeviceRead)
async def update_device(
    request: Request,
    device_id: str,
    payload: TechnicalDeviceUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> TechnicalDeviceRead:
    """Правка сведений, внесение заключения ЭПБ и вывод из эксплуатации."""

    TenantContextValidator.ensure_tenant_context(tenant)
    device = await _get_device_or_404(session, tenant, device_id)
    data = payload.model_dump(exclude_unset=True)
    await _validate_facility(session, tenant, data.get("facility_id"))
    _validate_device_dictionaries(
        kind=data.get("kind"), status_value=data.get("status")
    )
    today = date.today()
    before = _device_read(device, today).model_dump()
    for field in (
        "facility_id",
        "kind",
        "name",
        "serial_number",
        "commissioned_on",
        "lifetime_until",
        "epb_conclusion_number",
        "epb_registered_on",
        "epb_valid_until",
        "status",
        "notes",
    ):
        if field in data:
            value = data[field]
            if field in {"name", "facility_id"} and (
                value is None or not str(value).strip()
            ):
                raise _unprocessable(f"{field} cannot be empty")
            setattr(device, field, value.strip() if isinstance(value, str) else value)
    after = _device_read(device, today).model_dump()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="TechnicalDevice",
        object_id=device.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "TechnicalDevice"},
    )
    await session.commit()
    await session.refresh(device)
    return _device_read(device, date.today())


async def _last_work_map(
    session: AsyncSession, tenant: Tenant, device_ids: list[str]
) -> dict[str, tuple[date, str]]:
    """Последняя работа по каждому устройству — одним запросом, а не N+1.

    «Последняя» — по ДАТЕ РАБОТЫ, а не по порядку внесения: заключения вносят
    задним числом чаще, чем кажется (прецедент журнала работ контура ПБ).
    """

    if not device_ids:
        return {}
    ranked = (
        select(
            DeviceWorkRecord.device_id.label("device_id"),
            DeviceWorkRecord.performed_on.label("performed_on"),
            DeviceWorkRecord.result.label("result"),
            func.row_number()
            .over(
                partition_by=DeviceWorkRecord.device_id,
                order_by=(
                    DeviceWorkRecord.performed_on.desc(),
                    DeviceWorkRecord.created_at.desc(),
                ),
            )
            .label("rn"),
        )
        .where(
            DeviceWorkRecord.tenant_id == tenant.id,
            DeviceWorkRecord.deleted_at.is_(None),
            DeviceWorkRecord.device_id.in_(device_ids),
        )
        .subquery()
    )
    rows = await session.execute(
        select(ranked.c.device_id, ranked.c.performed_on, ranked.c.result).where(
            ranked.c.rn == 1
        )
    )
    return {row.device_id: (row.performed_on, row.result) for row in rows}


def _work_read(record: DeviceWorkRecord, *, shifted: bool) -> DeviceWorkRead:
    return DeviceWorkRead(
        id=record.id,
        device_id=record.device_id,
        kind=record.kind,
        kind_label=OPO_WORK_KINDS.get(record.kind, record.kind),
        performed_on=record.performed_on,
        result=record.result,
        result_label=OPO_WORK_RESULTS.get(record.result, record.result),
        performer=record.performer,
        conclusion_number=record.conclusion_number,
        notes=record.notes,
        next_due=record.next_due,
        shifted_due=shifted,
    )


def _work_shifts_due(kind: str, result: str, next_due: date | None) -> bool:
    """Продлевает ли работа эксплуатацию устройства.

    Только положительная ЭПБ: заключение о возможности дальнейшей безопасной
    эксплуатации даёт именно она. Диагностирование, освидетельствование, ТО и
    ремонт срок НЕ двигают — иначе «протёрли и записали ТО» продлевало бы
    жизнь устройству на бумаге. Отрицательный результат не двигает срок ни у
    какого вида: «не пригодно, но эксплуатировать ещё пять лет» — не вывод
    экспертизы.
    """

    return (
        kind == OPO_WORK_KIND_EXTENDING_EPB
        and result in OPO_WORK_PASSING_RESULTS
        and next_due is not None
    )


@router.get("/device-works", response_model=DeviceWorkPage)
async def list_device_works(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    device_id: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> DeviceWorkPage:
    """История работ: то самое доказательство, которого не было до среза."""

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(DeviceWorkRecord).where(
        DeviceWorkRecord.tenant_id == tenant.id,
        DeviceWorkRecord.deleted_at.is_(None),
    )
    if device_id:
        stmt = stmt.where(DeviceWorkRecord.device_id == device_id)
    if kind:
        stmt = stmt.where(DeviceWorkRecord.kind == kind)
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        (
            await session.execute(
                stmt.order_by(
                    DeviceWorkRecord.performed_on.desc(),
                    DeviceWorkRecord.created_at.desc(),
                )
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return DeviceWorkPage(
        items=[
            _work_read(
                r, shifted=_work_shifts_due(r.kind, r.result, r.next_due)
            )
            for r in rows
        ],
        total=total,
    )


@router.post(
    "/device-works", response_model=DeviceWorkRead, status_code=status.HTTP_201_CREATED
)
async def record_device_work(
    request: Request,
    payload: DeviceWorkCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> DeviceWorkRead:
    """Запись о выполненной работе — и единственный обоснованный перенос срока.

    Заключение ЭПБ вносится ЗДЕСЬ и само переносит срок дальнейшей безопасной
    эксплуатации вместе с реквизитами заключения: до этого среза срок можно
    было сдвинуть голой правкой поля, и «экспертиза проведена» ничем не
    отличалось от «экспертизы не было, но дату поправили».
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    device = await _get_device_or_404(session, tenant, payload.device_id)
    if payload.kind not in OPO_WORK_KINDS:
        raise _unprocessable(
            f"Неизвестный вид работы {payload.kind!r}; допустимые: "
            f"{', '.join(OPO_WORK_KINDS)}"
        )
    if payload.result not in OPO_WORK_RESULTS:
        raise _unprocessable(
            f"Неизвестный результат {payload.result!r}; допустимые: "
            f"{', '.join(OPO_WORK_RESULTS)}"
        )
    if payload.performed_on > date.today():
        raise _unprocessable(
            "Дата работы не может быть в будущем — запись о работе это "
            "свидетельство, а не план"
        )
    if payload.kind == OPO_WORK_KIND_EXTENDING_EPB and not (
        payload.conclusion_number and payload.conclusion_number.strip()
    ):
        raise _unprocessable(
            "Для экспертизы обязателен номер заключения: именно он вносится в "
            "реестр Ростехнадзора и предъявляется проверяющему"
        )

    record = DeviceWorkRecord(
        tenant_id=str(tenant.id),
        device_id=device.id,
        kind=payload.kind,
        performed_on=payload.performed_on,
        performer=(payload.performer or None),
        result=payload.result,
        conclusion_number=(payload.conclusion_number or None),
        notes=(payload.notes or None),
        next_due=payload.next_due,
    )
    session.add(record)

    shifted = _work_shifts_due(payload.kind, payload.result, payload.next_due)
    if shifted:
        device.epb_valid_until = payload.next_due
        device.epb_conclusion_number = record.conclusion_number
        device.epb_registered_on = payload.performed_on

    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="DeviceWorkRecord",
        object_id=record.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": record.id}}},
        details={
            "entity": "DeviceWorkRecord",
            "kind": record.kind,
            "device_id": device.id,
            "shifted_due": shifted,
        },
    )
    await session.commit()
    await session.refresh(record)
    return _work_read(record, shifted=shifted)


def _validity_status(expires_at: date | None, today: date) -> str:
    """Состояние срока аттестации — считается ПРИ ЧТЕНИИ.

    «Срока нет» — отдельное состояние (``absent``), а не «всё в порядке»:
    аттестация действует пять лет, и запись без даты окончания означает, что
    сведения неполны, а не что допуск бессрочный.
    """

    if expires_at is None:
        return "absent"
    if expires_at < today:
        return "overdue"
    if expires_at <= today + timedelta(days=_DUE_SOON_DAYS):
        return "due_soon"
    return "ok"


@router.get("/attestations", response_model=OpoAttestationPage)
async def list_attestations(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    area_code: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OpoAttestationPage:
    """Аттестация по промбезопасности: СВОИ записи ядрового реестра.

    Дисциплина не заводит своей таблицы — запись живёт в ядре
    (``Attestation``).

    ОТБОР ИДЁТ ПО ДИСЦИПЛИНЕ, А НЕ ПО «ЗАПОЛНЕНА ЛИ ОБЛАСТЬ». Раньше здесь
    стояло ``area_code IS NOT NULL`` с рассуждением «аттестация без области
    принадлежит другой дисциплине». Рассуждение было верным ровно до тех пор,
    пока в справочнике жили ТОЛЬКО области Ростехнадзора: тогда «область есть»
    и означало «это промбез». Разд. 56.2 срез-6 завёл в том же справочнике
    область «ПДД» — и старое правило втащило бы проверку знаний водителя на
    экран опасных производственных объектов как аттестацию по
    промбезопасности.

    Это тот же класс, что причина для ГО и ЧС в срезе-1 контура БДД: условие,
    верное на момент написания, протухает от одного расширения, и заметить
    это некому. Поэтому отбор берёт коды СВОЕЙ дисциплины из общей разметки.

    Экрана у ядровых аттестаций нет ни одного (в интерфейсе есть лишь тип
    задачи «Аттестации»), поэтому до среза 54.2 их не было видно нигде.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    today = date.today()
    stmt = (
        select(Attestation, Person.last_name, Person.first_name, Person.middle_name)
        .join(Person, Person.id == Attestation.person_id)
        .where(
            Attestation.tenant_id == tenant.id,
            Attestation.deleted_at.is_(None),
            Attestation.area_code.in_(
                areas_of_discipline(Discipline.INDUSTRIAL_SAFETY)
            ),
        )
    )
    if area_code:
        stmt = stmt.where(Attestation.area_code == area_code)
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        await session.execute(
            stmt.order_by(Attestation.expires_at.asc().nullslast()).offset(offset).limit(limit)
        )
    ).all()
    items = [
        OpoAttestationRead(
            id=record.id,
            person_id=record.person_id,
            # ФИО собирается здесь: у Person нет готового поля с полным именем,
            # а показывать человека идентификатором на экране нельзя.
            person_name=" ".join(
                part for part in (last_name, first_name, middle_name) if part
            ),
            name=record.name,
            area_code=record.area_code or "",
            area_label=ATTESTATION_AREA_TITLES.get(
                record.area_code or "", record.area_code or ""
            ),
            issued_at=record.issued_at,
            expires_at=record.expires_at,
            validity_status=_validity_status(record.expires_at, today),
            validity_status_label=OPO_ATTESTATION_STATUS_TITLES.get(
                _validity_status(record.expires_at, today),
                _validity_status(record.expires_at, today),
            ),
        )
        for record, last_name, first_name, middle_name in rows
    ]
    return OpoAttestationPage(items=items, total=total)


def _measure_status(measure: ProductionControlMeasure, today: date) -> str:
    """planned / overdue / done / cancelled — «просрочено» СЧИТАЕТСЯ при чтении.

    Хранить просрочку полем нельзя: срок наступает сам, без запроса на
    изменение, и хранимая метка разъехалась бы с календарём в первую же ночь
    (тот же довод, что у состояния тренировок в контуре ПБ).
    """

    if measure.status in {"done", "cancelled"}:
        return measure.status
    return "overdue" if measure.due_on < today else "planned"


def _measure_read(measure: ProductionControlMeasure, today: date) -> PcMeasureRead:
    status_value = _measure_status(measure, today)
    return PcMeasureRead(
        id=measure.id,
        plan_id=measure.plan_id,
        section=measure.section,
        section_label=PC_MEASURE_SECTIONS.get(measure.section, measure.section),
        title=measure.title,
        due_on=measure.due_on,
        responsible=measure.responsible,
        status=status_value,
        status_label=PC_MEASURE_STATUS_TITLES.get(status_value, status_value),
        completed_on=measure.completed_on,
        result=measure.result,
    )


async def _get_plan_or_404(
    session: AsyncSession, tenant: Tenant, plan_id: str
) -> ProductionControlPlan:
    stmt = select(ProductionControlPlan).where(
        ProductionControlPlan.id == plan_id,
        ProductionControlPlan.tenant_id == tenant.id,
        ProductionControlPlan.deleted_at.is_(None),
    )
    plan = (await session.execute(stmt)).scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="PC_PLAN_NOT_FOUND",
                message="Production control plan not found",
                error_type="industrial_safety",
            ),
        )
    return plan


async def _get_measure_or_404(
    session: AsyncSession, tenant: Tenant, measure_id: str
) -> ProductionControlMeasure:
    stmt = select(ProductionControlMeasure).where(
        ProductionControlMeasure.id == measure_id,
        ProductionControlMeasure.tenant_id == tenant.id,
        ProductionControlMeasure.deleted_at.is_(None),
    )
    measure = (await session.execute(stmt)).scalar_one_or_none()
    if measure is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="PC_MEASURE_NOT_FOUND",
                message="Production control measure not found",
                error_type="industrial_safety",
            ),
        )
    return measure


async def _ensure_plan_year_free(
    session: AsyncSession, tenant: Tenant, year: int, *, exclude_id: str | None = None
) -> None:
    """План ПК — годовой документ: второй на тот же год это дубль."""

    stmt = select(ProductionControlPlan.id).where(
        ProductionControlPlan.tenant_id == tenant.id,
        ProductionControlPlan.year == year,
        ProductionControlPlan.deleted_at.is_(None),
    )
    if exclude_id:
        stmt = stmt.where(ProductionControlPlan.id != exclude_id)
    if (await session.execute(stmt)).scalar_one_or_none() is not None:
        raise _unprocessable(f"План производственного контроля на {year} год уже заведён")


async def _plan_read(
    session: AsyncSession, tenant: Tenant, plan: ProductionControlPlan, today: date
) -> PcPlanRead:
    measures = (
        (
            await session.execute(
                select(ProductionControlMeasure).where(
                    ProductionControlMeasure.tenant_id == tenant.id,
                    ProductionControlMeasure.plan_id == plan.id,
                    ProductionControlMeasure.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    return PcPlanRead(
        id=plan.id,
        year=plan.year,
        title=plan.title,
        responsible=plan.responsible,
        approved_on=plan.approved_on,
        status=plan.status,
        status_label=PC_PLAN_STATUSES.get(plan.status, plan.status),
        notes=plan.notes,
        measures_total=len(measures),
        measures_overdue=sum(
            1 for m in measures if _measure_status(m, today) == "overdue"
        ),
    )


@router.get("/pc-plans", response_model=PcPlanPage)
async def list_pc_plans(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    year: int | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PcPlanPage:
    """Планы производственного контроля по годам."""

    TenantContextValidator.ensure_tenant_context(tenant)
    today = date.today()
    stmt = select(ProductionControlPlan).where(
        ProductionControlPlan.tenant_id == tenant.id,
        ProductionControlPlan.deleted_at.is_(None),
    )
    if year:
        stmt = stmt.where(ProductionControlPlan.year == year)
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        (
            await session.execute(
                stmt.order_by(ProductionControlPlan.year.desc()).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return PcPlanPage(
        items=[await _plan_read(session, tenant, plan, today) for plan in rows],
        total=total,
    )


@router.post("/pc-plans", response_model=PcPlanRead, status_code=status.HTTP_201_CREATED)
async def create_pc_plan(
    request: Request,
    payload: PcPlanCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> PcPlanRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    if payload.status not in PC_PLAN_STATUSES:
        raise _unprocessable(
            f"Неизвестное состояние {payload.status!r}; допустимые: "
            f"{', '.join(PC_PLAN_STATUSES)}"
        )
    await _ensure_plan_year_free(session, tenant, payload.year)

    plan = ProductionControlPlan(
        tenant_id=str(tenant.id),
        year=payload.year,
        title=payload.title.strip(),
        responsible=(payload.responsible or None),
        approved_on=payload.approved_on,
        status=payload.status or "draft",
        notes=(payload.notes or None),
    )
    session.add(plan)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="ProductionControlPlan",
        object_id=plan.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": plan.id}}},
        details={"entity": "ProductionControlPlan", "year": plan.year},
    )
    await session.commit()
    await session.refresh(plan)
    return await _plan_read(session, tenant, plan, date.today())


@router.patch("/pc-plans/{plan_id}", response_model=PcPlanRead)
async def update_pc_plan(
    request: Request,
    plan_id: str,
    payload: PcPlanUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> PcPlanRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    plan = await _get_plan_or_404(session, tenant, plan_id)
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in PC_PLAN_STATUSES:
        raise _unprocessable(
            f"Неизвестное состояние {data['status']!r}; допустимые: "
            f"{', '.join(PC_PLAN_STATUSES)}"
        )
    if "year" in data and data["year"]:
        await _ensure_plan_year_free(session, tenant, int(data["year"]), exclude_id=plan.id)

    today = date.today()
    before = (await _plan_read(session, tenant, plan, today)).model_dump()
    for field in ("year", "title", "responsible", "approved_on", "status", "notes"):
        if field in data:
            value = data[field]
            if field == "title" and (value is None or not str(value).strip()):
                raise _unprocessable("title cannot be empty")
            setattr(plan, field, value.strip() if isinstance(value, str) else value)
    after = (await _plan_read(session, tenant, plan, today)).model_dump()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="ProductionControlPlan",
        object_id=plan.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "ProductionControlPlan"},
    )
    await session.commit()
    await session.refresh(plan)
    return await _plan_read(session, tenant, plan, date.today())


def _validate_measure(
    *, section: str | None, status_value: str | None, completed_on: date | None, is_done: bool
) -> None:
    if section is not None and section not in PC_MEASURE_SECTIONS:
        raise _unprocessable(
            f"Неизвестный раздел {section!r}; допустимые: {', '.join(PC_MEASURE_SECTIONS)}"
        )
    if status_value is not None and status_value not in PC_MEASURE_WRITABLE_STATUSES:
        raise _unprocessable(
            f"Неизвестное состояние {status_value!r}; допустимые: "
            f"{', '.join(PC_MEASURE_WRITABLE_STATUSES)}"
        )
    if completed_on is not None and completed_on > date.today():
        raise _unprocessable(
            "Дата выполнения не может быть в будущем — это план, а не отчёт"
        )
    if is_done and completed_on is None:
        raise _unprocessable(
            "У выполненного мероприятия обязательна дата выполнения: именно она "
            "предъявляется надзору как доказательство исполнения плана"
        )


@router.get("/pc-measures", response_model=PcMeasurePage)
async def list_pc_measures(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    plan_id: str | None = Query(default=None),
    section: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PcMeasurePage:
    """Мероприятия плана: что, к какому сроку, кто и с каким результатом."""

    TenantContextValidator.ensure_tenant_context(tenant)
    today = date.today()
    stmt = select(ProductionControlMeasure).where(
        ProductionControlMeasure.tenant_id == tenant.id,
        ProductionControlMeasure.deleted_at.is_(None),
    )
    if plan_id:
        stmt = stmt.where(ProductionControlMeasure.plan_id == plan_id)
    if section:
        stmt = stmt.where(ProductionControlMeasure.section == section)
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        (
            await session.execute(
                stmt.order_by(ProductionControlMeasure.due_on).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return PcMeasurePage(items=[_measure_read(r, today) for r in rows], total=total)


@router.post(
    "/pc-measures", response_model=PcMeasureRead, status_code=status.HTTP_201_CREATED
)
async def create_pc_measure(
    request: Request,
    payload: PcMeasureCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> PcMeasureRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    plan = (
        await session.execute(
            select(ProductionControlPlan.id).where(
                ProductionControlPlan.id == payload.plan_id,
                ProductionControlPlan.tenant_id == tenant.id,
                ProductionControlPlan.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if plan is None:
        raise _unprocessable("План не найден")
    _validate_measure(
        section=payload.section,
        status_value=payload.status,
        completed_on=payload.completed_on,
        is_done=payload.status == "done",
    )

    measure = ProductionControlMeasure(
        tenant_id=str(tenant.id),
        plan_id=payload.plan_id,
        section=payload.section,
        title=payload.title.strip(),
        due_on=payload.due_on,
        responsible=(payload.responsible or None),
        status=payload.status or "planned",
        completed_on=payload.completed_on,
        result=(payload.result or None),
    )
    session.add(measure)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="ProductionControlMeasure",
        object_id=measure.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": measure.id}}},
        details={"entity": "ProductionControlMeasure", "section": measure.section},
    )
    await session.commit()
    await session.refresh(measure)
    return _measure_read(measure, date.today())


@router.patch("/pc-measures/{measure_id}", response_model=PcMeasureRead)
async def update_pc_measure(
    request: Request,
    measure_id: str,
    payload: PcMeasureUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> PcMeasureRead:
    """Отметка выполнения и правка мероприятия."""

    TenantContextValidator.ensure_tenant_context(tenant)
    measure = await _get_measure_or_404(session, tenant, measure_id)
    data = payload.model_dump(exclude_unset=True)
    if "plan_id" in data and data["plan_id"]:
        plan = (
            await session.execute(
                select(ProductionControlPlan.id).where(
                    ProductionControlPlan.id == data["plan_id"],
                    ProductionControlPlan.tenant_id == tenant.id,
                    ProductionControlPlan.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if plan is None:
            raise _unprocessable("План не найден")
    # Проверяем ИТОГОВОЕ состояние записи, а не только присланные поля: иначе
    # «выполнено» одним запросом и дата другим прошли бы оба, оставив запись
    # без свидетельства (прецедент тренировок контура ПБ).
    next_status = data["status"] if "status" in data else measure.status
    next_completed = (
        data["completed_on"] if "completed_on" in data else measure.completed_on
    )
    _validate_measure(
        section=data.get("section"),
        status_value=data.get("status"),
        completed_on=next_completed,
        is_done=next_status == "done",
    )

    today = date.today()
    before = _measure_read(measure, today).model_dump()
    for field in (
        "plan_id",
        "section",
        "title",
        "due_on",
        "responsible",
        "status",
        "completed_on",
        "result",
    ):
        if field in data:
            value = data[field]
            if field == "title" and (value is None or not str(value).strip()):
                raise _unprocessable("title cannot be empty")
            setattr(measure, field, value.strip() if isinstance(value, str) else value)
    after = _measure_read(measure, today).model_dump()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="ProductionControlMeasure",
        object_id=measure.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "ProductionControlMeasure"},
    )
    await session.commit()
    await session.refresh(measure)
    return _measure_read(measure, date.today())


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

    # Разд. 54.2 «технические устройства… ЭПБ, сроки». Считаем ТОЛЬКО
    # эксплуатируемые: списанное устройство просрочкой быть не может.
    today = date.today()
    devices = (
        (
            await session.execute(
                select(TechnicalDevice).where(
                    TechnicalDevice.tenant_id == tenant.id,
                    TechnicalDevice.deleted_at.is_(None),
                    TechnicalDevice.status != "decommissioned",
                )
            )
        )
        .scalars()
        .all()
    )
    epb_overdue = sum(1 for d in devices if _epb_status(d, today) == "overdue")
    epb_due_soon = sum(1 for d in devices if _epb_status(d, today) == "due_soon")
    # ФАКТ, а не суждение: назначенный срок службы истёк И действующего
    # заключения нет. Обязана ли экспертиза быть проведена, платформа не
    # решает — это зависит от типа устройства, документации и норм ФНП,
    # которых в данных нет (тот же довод, что у интервала тренировок).
    past_lifetime_without_epb = sum(
        1
        for d in devices
        if d.lifetime_until is not None
        and d.lifetime_until < today
        and _epb_status(d, today) in {"absent", "overdue"}
    )

    # Разд. 54.2 «история работ»: срок без единой записи о работах — обещание,
    # а не доказательство. Инспектор просит показать заключение по предыдущей
    # экспертизе, а не назвать дату следующей.
    confirmed_ids = set(
        (
            await session.execute(
                select(DeviceWorkRecord.device_id.distinct()).where(
                    DeviceWorkRecord.tenant_id == tenant.id,
                    DeviceWorkRecord.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    devices_without_work = sum(1 for d in devices if d.id not in confirmed_ids)

    # Разд. 54.2 «аттестация персонала»: считаем записи СВОЕЙ дисциплины.
    #
    # Здесь стояло ``area_code IS NOT NULL`` с доводом «у аттестаций других
    # дисциплин области нет». Он был верен, пока справочник был перечнем
    # Ростехнадзора; разд. 56.2 срез-6 завёл в нём область «ПДД», и просроченная
    # проверка знаний водителя попала бы в счётчик просроченных аттестаций по
    # ПРОМБЕЗОПАСНОСТИ — то есть в число, по которому готовятся к проверке
    # Ростехнадзора. ВТОРОЕ такое место в этом же файле (список аттестаций)
    # починено тем же приёмом: отбор по дисциплине, а не по заполненности поля.
    attestations = (
        (
            await session.execute(
                select(Attestation).where(
                    Attestation.tenant_id == tenant.id,
                    Attestation.deleted_at.is_(None),
                    Attestation.area_code.in_(
                        areas_of_discipline(Discipline.INDUSTRIAL_SAFETY)
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    attestations_overdue = sum(
        1 for a in attestations if _validity_status(a.expires_at, today) == "overdue"
    )
    attestations_due_soon = sum(
        1 for a in attestations if _validity_status(a.expires_at, today) == "due_soon"
    )

    # Разд. 54.2 «производственный контроль». ГРАНИЦА: отдаём ФАКТ наличия
    # плана на текущий год, а не приговор — обязанность вести ПК зависит от
    # того, эксплуатирует ли организация ОПО, и полноту сведений определяет
    # специалист (тот же довод, что у интервала тренировок и требования ЭПБ).
    current_plan = (
        await session.execute(
            select(ProductionControlPlan.id).where(
                ProductionControlPlan.tenant_id == tenant.id,
                ProductionControlPlan.deleted_at.is_(None),
                ProductionControlPlan.year == today.year,
            )
        )
    ).scalar_one_or_none()
    measures = (
        (
            await session.execute(
                select(ProductionControlMeasure).where(
                    ProductionControlMeasure.tenant_id == tenant.id,
                    ProductionControlMeasure.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    pc_overdue = sum(1 for m in measures if _measure_status(m, today) == "overdue")
    pc_planned = sum(1 for m in measures if _measure_status(m, today) == "planned")

    return IndustrialReadinessRead(
        current_year_plan_exists=current_plan is not None,
        pc_measures_overdue=pc_overdue,
        pc_measures_planned=pc_planned,
        attestations_total=len(attestations),
        attestations_overdue=attestations_overdue,
        attestations_due_soon=attestations_due_soon,
        devices_without_work_record=devices_without_work,
        total_facilities=len(active),
        by_class=by_class,
        excluded_facilities=len(rows) - len(active),
        total_devices=len(devices),
        epb_overdue=epb_overdue,
        epb_due_soon=epb_due_soon,
        devices_past_lifetime_without_epb=past_lifetime_without_epb,
        # Доп. №1 разд. 57.4: открытые происшествия контура — той же формулой,
        # что разрез «по дисциплинам» у директора (срез-49).
        incidents_open=await open_incidents_count(
            session, str(tenant.id), Discipline.INDUSTRIAL_SAFETY
        ),
    )
