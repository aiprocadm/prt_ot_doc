"""Контур БДД, собственные ручки (Доп. №1 разд. 56.2, срезы 1–4).

Реестр транспортных средств (срез-1), карточки водителей (срез-2) и путевые
листы с отметками контроля (срез-3) и учёт ДТП (срез-4). До среза-1 по разд.
56.2 не было ни одной
модели транспорта — ТЗ отсылало к «transport safety (vNext §17.3)», которого в
коде не существовало.

Гейт модуля — роутерный (разд. 61.3): на каждом роуте по построению,
аутентификация РАНЬШЕ гейта (иначе без токена вернулся бы 404 вместо 401),
отключённый (но выдававшийся) модуль читается (read-only, BIZ-61 срез-6).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_session, get_tenant_record
from app.core.disciplines import BRIEFING_TYPE_DISCIPLINE, Discipline
from app.core.errors import api_problem_detail
from app.core.feature_flags import is_module_enabled, raise_for_disabled_module
from app.core.security import AccessContext, abac, rbac
from app.core.tenant_validation import TenantContextValidator
from app.models.briefings import BriefingEntry
from app.models.incidents import Incident
from app.models.master_data import Person, Site
from app.models.models import Tenant
from app.models.road_safety import (
    ACCIDENT_CAPA_SOURCE,
    ACCIDENT_CONSEQUENCE_TITLES,
    ACCIDENT_FAULT,
    ACCIDENT_FOLLOWUP_TITLES,
    ACCIDENT_KINDS,
    DRIVER_LICENSE_CATEGORIES,
    DRIVER_STATUSES,
    TACHOGRAPH_STATUS_TITLES,
    VEHICLE_DOC_STATUS_TITLES,
    VEHICLE_KINDS,
    VEHICLE_STATUSES,
    WAYBILL_MARK_STATUSES,
    WAYBILL_RELEASE_TITLES,
    WAYBILL_STATUSES,
    Driver,
    RoadAccident,
    Vehicle,
    Waybill,
)
from app.models.safety_ops import CorrectiveAction
from app.schemas.road_safety import (
    DriverCreate,
    DriverPage,
    DriverRead,
    DriverUpdate,
    RoadAccidentCreate,
    RoadAccidentPage,
    RoadAccidentRead,
    RoadAccidentUpdate,
    RoadSafetyReadinessRead,
    VehicleCreate,
    VehiclePage,
    VehicleRead,
    VehicleUpdate,
    WaybillCreate,
    WaybillPage,
    WaybillRead,
    WaybillUpdate,
)
from app.services.audit import AuditService, field_level_diff

router = APIRouter(prefix="/road-safety", tags=["road-safety"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_ROLES = ["admin", "owner", "ot_pb_lead", "ot_specialist"]

#: горизонт «скоро истекает» — тот же, что у остальных сводок продукта
_DUE_SOON_DAYS = 30

#: окно сводки по ДТП — ГОДОВОЕ, а не месячное как у листов. ДТП редки: за
#: месяц их у большинства арендаторов ноль, и по такому окну об аварийности
#: судить нельзя. Год — стандартный горизонт её анализа.
_ACCIDENT_WINDOW_DAYS = 365

#: окно сводки по путевым листам. Парк и водительский состав считаются
#: ЦЕЛИКОМ — их десятки; листов же выписывается по одному на машину за смену,
#: и «всего листов за всё время» ни о чём не говорит.
_WAYBILL_WINDOW_DAYS = 30


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


Access = Annotated[
    AccessContext,
    Depends(
        abac(_tenant_resource_id, required_roles=_ROLES, action="manage road safety")
    ),
]

_FEATURE_CODE = "road_safety"


async def _require_road_safety(
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
            error_type="road_safety",
            disabled_code="ROAD_SAFETY_DISABLED",
            disabled_message="Road safety module is not enabled for this tenant",
        )


router.dependencies.append(Depends(_require_road_safety))


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(
            code="ROAD_SAFETY_VALIDATION_ERROR",
            message=message,
            error_type="road_safety",
        ),
    )


def _doc_status(due: date | None, today: date) -> str:
    """missing / ok / due_soon / overdue — считается ПРИ ЧТЕНИИ.

    ОТЛИЧИЕ от документов ПБ и ГО, где пустой срок означал БЕССРОЧНО: у
    диагностической карты и полиса ОСАГО бессрочности НЕ БЫВАЕТ. Пустая дата
    значит только, что сведений нет — и это НЕ «просрочено»: «мы не знаем» и
    «истекло» разные утверждения, и путать их нельзя.
    """

    if due is None:
        return "missing"
    if due < today:
        return "overdue"
    if due <= today + timedelta(days=_DUE_SOON_DAYS):
        return "due_soon"
    return "ok"


def _tachograph_status(vehicle: Vehicle, today: date) -> str:
    """Отсутствие прибора и отсутствие сведений о поверке — разные факты.

    ГРАНИЦА: платформа НЕ решает, нужен ли тахограф на этой машине.
    """

    if not vehicle.tachograph_installed:
        return "not_installed"
    return _doc_status(vehicle.tachograph_due, today)


def _vehicle_read(vehicle: Vehicle, today: date) -> VehicleRead:
    inspection = _doc_status(vehicle.inspection_due, today)
    insurance = _doc_status(vehicle.insurance_due, today)
    tachograph = _tachograph_status(vehicle, today)
    return VehicleRead(
        id=vehicle.id,
        plate_number=vehicle.plate_number,
        brand_model=vehicle.brand_model,
        kind=vehicle.kind,
        kind_label=VEHICLE_KINDS.get(vehicle.kind, vehicle.kind),
        status=vehicle.status,
        status_label=VEHICLE_STATUSES.get(vehicle.status, vehicle.status),
        vin=vehicle.vin,
        year_made=vehicle.year_made,
        site_id=vehicle.site_id,
        inspection_due=vehicle.inspection_due,
        insurance_due=vehicle.insurance_due,
        license_number=vehicle.license_number,
        license_due=vehicle.license_due,
        tachograph_installed=vehicle.tachograph_installed,
        tachograph_due=vehicle.tachograph_due,
        notes=vehicle.notes,
        inspection_status=inspection,
        inspection_status_label=VEHICLE_DOC_STATUS_TITLES.get(inspection, inspection),
        insurance_status=insurance,
        insurance_status_label=VEHICLE_DOC_STATUS_TITLES.get(insurance, insurance),
        tachograph_status=tachograph,
        tachograph_status_label=TACHOGRAPH_STATUS_TITLES.get(tachograph, tachograph),
    )


def _validate_dictionaries(*, kind: str | None, status_value: str | None) -> None:
    if kind is not None and kind not in VEHICLE_KINDS:
        raise _unprocessable(
            f"Неизвестный вид ТС {kind!r}; допустимые: {', '.join(VEHICLE_KINDS)}"
        )
    if status_value is not None and status_value not in VEHICLE_STATUSES:
        raise _unprocessable(
            f"Неизвестное состояние {status_value!r}; допустимые: "
            f"{', '.join(VEHICLE_STATUSES)}"
        )


async def _get_vehicle_or_404(
    session: AsyncSession, tenant: Tenant, vehicle_id: str
) -> Vehicle:
    stmt = select(Vehicle).where(
        Vehicle.id == vehicle_id,
        Vehicle.tenant_id == tenant.id,
        Vehicle.deleted_at.is_(None),
    )
    vehicle = (await session.execute(stmt)).scalar_one_or_none()
    if vehicle is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="VEHICLE_NOT_FOUND",
                message="Vehicle not found",
                error_type="road_safety",
            ),
        )
    return vehicle


async def _ensure_plate_free(
    session: AsyncSession,
    tenant: Tenant,
    plate_number: str,
    *,
    exclude_id: str | None = None,
) -> None:
    """Одна машина — одна запись: второй такой же номер это ошибка ввода."""

    stmt = select(Vehicle.id).where(
        Vehicle.tenant_id == tenant.id,
        Vehicle.plate_number == plate_number,
        Vehicle.deleted_at.is_(None),
    )
    if exclude_id:
        stmt = stmt.where(Vehicle.id != exclude_id)
    if (await session.execute(stmt)).scalar_one_or_none() is not None:
        raise _unprocessable(f"ТС с номером {plate_number!r} уже заведено")


async def _validate_site(
    session: AsyncSession, tenant: Tenant, site_id: str | None
) -> None:
    if not site_id:
        return
    stmt = select(Site.id).where(
        Site.id == site_id, Site.tenant_id == tenant.id, Site.deleted_at.is_(None)
    )
    if (await session.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="SITE_NOT_FOUND",
                message="Site not found",
                error_type="road_safety",
            ),
        )


@router.get("/vehicles", response_model=VehiclePage)
async def list_vehicles(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    kind: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> VehiclePage:
    """Реестр парка: и эксплуатируемые, и списанные — история цела."""

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(Vehicle).where(
        Vehicle.tenant_id == tenant.id, Vehicle.deleted_at.is_(None)
    )
    if kind:
        stmt = stmt.where(Vehicle.kind == kind)
    if status_filter:
        stmt = stmt.where(Vehicle.status == status_filter)
    total = int(
        await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )
    rows = (
        (
            await session.execute(
                stmt.order_by(Vehicle.plate_number).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    today = date.today()
    return VehiclePage(items=[_vehicle_read(r, today) for r in rows], total=total)


@router.post("/vehicles", response_model=VehicleRead, status_code=status.HTTP_201_CREATED)
async def create_vehicle(
    request: Request,
    payload: VehicleCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> VehicleRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _validate_dictionaries(kind=payload.kind, status_value=payload.status)
    await _validate_site(session, tenant, payload.site_id)
    plate = payload.plate_number.strip().upper()
    await _ensure_plate_free(session, tenant, plate)

    vehicle = Vehicle(
        tenant_id=str(tenant.id),
        plate_number=plate,
        brand_model=payload.brand_model.strip(),
        kind=payload.kind,
        status=payload.status,
        vin=(payload.vin or None),
        year_made=payload.year_made,
        site_id=payload.site_id or None,
        inspection_due=payload.inspection_due,
        insurance_due=payload.insurance_due,
        license_number=(payload.license_number or None),
        license_due=payload.license_due,
        tachograph_installed=payload.tachograph_installed,
        tachograph_due=payload.tachograph_due,
        notes=(payload.notes or None),
    )
    session.add(vehicle)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="Vehicle",
        object_id=vehicle.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": vehicle.id}}},
        details={"entity": "Vehicle", "plate_number": vehicle.plate_number},
    )
    await session.commit()
    await session.refresh(vehicle)
    return _vehicle_read(vehicle, date.today())


@router.patch("/vehicles/{vehicle_id}", response_model=VehicleRead)
async def update_vehicle(
    request: Request,
    vehicle_id: str,
    payload: VehicleUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> VehicleRead:
    """Правка сведений. Списание — смена СОСТОЯНИЯ, а не удаление записи."""

    TenantContextValidator.ensure_tenant_context(tenant)
    vehicle = await _get_vehicle_or_404(session, tenant, vehicle_id)
    data = payload.model_dump(exclude_unset=True)
    _validate_dictionaries(kind=data.get("kind"), status_value=data.get("status"))
    before = {
        "plate_number": vehicle.plate_number,
        "brand_model": vehicle.brand_model,
        "kind": vehicle.kind,
        "status": vehicle.status,
        "inspection_due": str(vehicle.inspection_due),
        "insurance_due": str(vehicle.insurance_due),
        "tachograph_installed": vehicle.tachograph_installed,
        "tachograph_due": str(vehicle.tachograph_due),
    }
    if data.get("plate_number"):
        plate = str(data["plate_number"]).strip().upper()
        await _ensure_plate_free(session, tenant, plate, exclude_id=vehicle.id)
        vehicle.plate_number = plate
    if data.get("brand_model"):
        vehicle.brand_model = str(data["brand_model"]).strip()
    if data.get("kind"):
        vehicle.kind = str(data["kind"])
    if data.get("status"):
        vehicle.status = str(data["status"])
    if "site_id" in data:
        await _validate_site(session, tenant, data["site_id"])
        vehicle.site_id = data["site_id"] or None
    if data.get("tachograph_installed") is not None:
        vehicle.tachograph_installed = bool(data["tachograph_installed"])
    if "year_made" in data:
        vehicle.year_made = data["year_made"]
    for field in ("inspection_due", "insurance_due", "license_due", "tachograph_due"):
        if field in data:
            setattr(vehicle, field, data[field])
    for field in ("vin", "license_number", "notes"):
        if field in data:
            setattr(vehicle, field, data[field] or None)
    await session.flush()
    after = {
        "plate_number": vehicle.plate_number,
        "brand_model": vehicle.brand_model,
        "kind": vehicle.kind,
        "status": vehicle.status,
        "inspection_due": str(vehicle.inspection_due),
        "insurance_due": str(vehicle.insurance_due),
        "tachograph_installed": vehicle.tachograph_installed,
        "tachograph_due": str(vehicle.tachograph_due),
    }
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="Vehicle",
        object_id=vehicle.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "Vehicle"},
    )
    await session.commit()
    await session.refresh(vehicle)
    return _vehicle_read(vehicle, date.today())


@router.get("/readiness", response_model=RoadSafetyReadinessRead)
async def road_safety_readiness(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> RoadSafetyReadinessRead:
    """Сводка БДД: парк, водительский состав, сроки, выпуск на линию и ДТП.

    Просрочки считаются ТОЛЬКО по ТС в эксплуатации и по ДОПУЩЕННЫМ водителям: у списанной машины
    просроченный полис это шум, а не проблема, и показывать его как нарушение
    значило бы отвлекать специалиста от настоящих.

    ГРАНИЦА: платформа НЕ решает, нужен ли тахограф и требуется ли лицензия.
    «Сведения не внесены» — факт о данных, а не вердикт о нарушении.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    rows = (
        (
            await session.execute(
                select(Vehicle).where(
                    Vehicle.tenant_id == tenant.id, Vehicle.deleted_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    today = date.today()
    by_status = {code: 0 for code in VEHICLE_STATUSES}
    for vehicle in rows:
        if vehicle.status in by_status:
            by_status[vehicle.status] += 1

    active = [v for v in rows if v.status == "in_service"]

    # Срез-2: водительский состав. Просрочки — ТОЛЬКО по допущенным: у
    # отстранённого водителя просроченное удостоверение это шум, а не
    # проблема (тот же довод, что у списанного ТС).
    drivers = (
        (
            await session.execute(
                select(Driver).where(
                    Driver.tenant_id == tenant.id, Driver.deleted_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    drivers_by_status = {code: 0 for code in DRIVER_STATUSES}
    for driver in drivers:
        if driver.status in drivers_by_status:
            drivers_by_status[driver.status] += 1
    admitted = [d for d in drivers if d.status == "admitted"]

    # Срез-3: путевые листы. В отличие от парка и водительского состава,
    # реестр листов растёт КАЖДУЮ СМЕНУ, поэтому сводка считается за окно и
    # SQL-агрегатами, а не выгрузкой всех строк в память: «сколько листов у
    # нас за три года» — не тот вопрос, на который смотрят утром.
    window_start = today - timedelta(days=_WAYBILL_WINDOW_DAYS)
    window = (
        Waybill.tenant_id == tenant.id,
        Waybill.deleted_at.is_(None),
        Waybill.issued_on >= window_start,
    )
    waybills_by_status = {code: 0 for code in WAYBILL_STATUSES}
    for code, count in (
        await session.execute(
            select(Waybill.status, func.count()).where(*window).group_by(Waybill.status)
        )
    ).all():
        if code in waybills_by_status:
            waybills_by_status[code] = int(count)

    # Аннулированный лист выпуском не считается: именно по нему видно, что
    # выезда не было, и записывать его в нарушения значило бы шуметь.
    live = (*window, Waybill.status != "cancelled")
    blocked = int(
        await session.scalar(
            select(func.count())
            .select_from(Waybill)
            .where(*live, _release_condition("blocked"))
        )
        or 0
    )
    # «Не внесено» и «не пройдено» не суммируются: лист с проваленным
    # осмотром — нарушение, лист с пустой отметкой — дыра в учёте. Поэтому
    # проваленные исключены из второго счётчика, а не посчитаны дважды.
    unconfirmed = int(
        await session.scalar(
            select(func.count())
            .select_from(Waybill)
            .where(*live, _release_condition("unconfirmed"))
        )
        or 0
    )

    # Срез-4: ДТП. Окно ГОДОВОЕ — за месяц у большинства арендаторов их ноль,
    # и по такому окну об аварийности судить нельзя.
    accident_start = today - timedelta(days=_ACCIDENT_WINDOW_DAYS)
    accidents = (
        (
            await session.execute(
                select(RoadAccident).where(
                    RoadAccident.tenant_id == tenant.id,
                    RoadAccident.deleted_at.is_(None),
                    RoadAccident.occurred_at
                    >= datetime.combine(accident_start, time.min, tzinfo=timezone.utc),
                )
            )
        )
        .scalars()
        .all()
    )
    by_consequences = {code: 0 for code in ACCIDENT_CONSEQUENCE_TITLES}
    for accident in accidents:
        by_consequences[_consequences(accident)] += 1
    accident_capa = await _capa_counts(session, tenant, [a.id for a in accidents])
    without_follow_up = sum(
        1
        for a in accidents
        if _follow_up(
            capa_total=accident_capa.get(a.id, (0, 0))[0],
            capa_open=accident_capa.get(a.id, (0, 0))[1],
            incident_id=a.incident_id,
        )
        == "not_started"
    )

    # Срез-5: инструктажи водителей по БДД. Свой реестр НЕ заводится — механизм
    # инструктажей есть в ядре, не хватало только видов БДД в закрытом словаре
    # (та же дыра, что закрыл разд. 54.1 для пожарной безопасности).
    #
    # ГРАНИЦА: платформа НЕ решает, кого и как часто инструктировать, — это
    # следует из вида перевозок и локальных приказов. Считается просроченное
    # по ВНЕСЁННОМУ сроку, а не по норме.
    road_briefing_types = [
        code
        for code, discipline in BRIEFING_TYPE_DISCIPLINE.items()
        if discipline is Discipline.ROAD_SAFETY
    ]
    briefings_total = int(
        await session.scalar(
            select(func.count())
            .select_from(BriefingEntry)
            .where(
                BriefingEntry.tenant_id == tenant.id,
                BriefingEntry.deleted_at.is_(None),
                BriefingEntry.briefing_type.in_(road_briefing_types),
            )
        )
        or 0
    )
    briefings_overdue = int(
        await session.scalar(
            select(func.count())
            .select_from(BriefingEntry)
            .where(
                BriefingEntry.tenant_id == tenant.id,
                BriefingEntry.deleted_at.is_(None),
                BriefingEntry.briefing_type.in_(road_briefing_types),
                BriefingEntry.valid_until.is_not(None),
                BriefingEntry.valid_until < func.now(),
            )
        )
        or 0
    )

    return RoadSafetyReadinessRead(
        total_vehicles=len(rows),
        by_status=by_status,
        inspection_overdue=sum(
            1 for v in active if _doc_status(v.inspection_due, today) == "overdue"
        ),
        insurance_overdue=sum(
            1 for v in active if _doc_status(v.insurance_due, today) == "overdue"
        ),
        tachograph_overdue=sum(
            1 for v in active if _tachograph_status(v, today) == "overdue"
        ),
        documents_missing=sum(
            1
            for v in active
            if _doc_status(v.inspection_due, today) == "missing"
            or _doc_status(v.insurance_due, today) == "missing"
        ),
        total_drivers=len(drivers),
        drivers_by_status=drivers_by_status,
        driver_license_overdue=sum(
            1 for d in admitted if _doc_status(d.license_due, today) == "overdue"
        ),
        driver_license_missing=sum(
            1 for d in admitted if _doc_status(d.license_due, today) == "missing"
        ),
        waybill_window_days=_WAYBILL_WINDOW_DAYS,
        waybills_total=sum(waybills_by_status.values()),
        waybills_by_status=waybills_by_status,
        waybills_release_blocked=blocked,
        waybills_release_unconfirmed=unconfirmed,
        accident_window_days=_ACCIDENT_WINDOW_DAYS,
        accidents_total=len(accidents),
        accidents_by_consequences=by_consequences,
        injured_total=sum(a.injured_count for a in accidents),
        fatalities_total=sum(a.fatalities_count for a in accidents),
        accidents_without_follow_up=without_follow_up,
        road_briefings_total=briefings_total,
        road_briefings_overdue=briefings_overdue,
    )


# ---------------------------------------------------------------------------
# Срез-2: водители (Доп. №1 разд. 56.2, пункт «Водители»)
#
# Человек НЕ дублируется: карточка ссылается на ядрового ``Person``, а ФИО и
# должность приходят в ответе из него. Второй список сотрудников разошёлся бы
# с первым на первой же кадровой правке.
# ---------------------------------------------------------------------------


def _experience_years(since: date | None, today: date) -> int | None:
    """Водительский стаж — СЧИТАЕТСЯ ПРИ ЧТЕНИИ, а не хранится числом.

    Записанное «стаж 3 года» через два года молча превращается в ложь: у числа
    нет даты, на которую оно верно. Хранится дата начала, число лет считается
    здесь — тем же приёмом, что просрочки в остальном продукте.
    """

    if since is None:
        return None
    years = today.year - since.year
    if (today.month, today.day) < (since.month, since.day):
        years -= 1
    return max(years, 0)


def _person_name(person: Person | None) -> str:
    if person is None:
        return ""
    parts = [person.last_name, person.first_name, person.middle_name]
    return " ".join(part for part in parts if part)


def _driver_read(driver: Driver, today: date) -> DriverRead:
    license_status = _doc_status(driver.license_due, today)
    person = driver.person
    return DriverRead(
        id=driver.id,
        person_id=driver.person_id,
        person_name=_person_name(person),
        personnel_number=getattr(person, "personnel_number", None),
        position_title=getattr(person, "position_title", None),
        license_number=driver.license_number,
        categories=list(driver.categories or []),
        category_labels=[
            DRIVER_LICENSE_CATEGORIES.get(code, code)
            for code in (driver.categories or [])
        ],
        license_issued_at=driver.license_issued_at,
        license_due=driver.license_due,
        experience_since=driver.experience_since,
        experience_years=_experience_years(driver.experience_since, today),
        status=driver.status,
        status_label=DRIVER_STATUSES.get(driver.status, driver.status),
        license_status=license_status,
        license_status_label=VEHICLE_DOC_STATUS_TITLES.get(
            license_status, license_status
        ),
        notes=driver.notes,
    )


def _validate_driver_dictionaries(
    *, categories: list[str] | None, status_value: str | None
) -> None:
    """Категории и допуск — только из закрытых словарей.

    Свободная строка здесь стоила бы того же, что стоила у вида инструктажа:
    «B», «в» и «кат. B» — три разные строки об одном, и вопрос «кто допущен к
    автобусу» остаётся без ответа.
    """

    if status_value is not None and status_value not in DRIVER_STATUSES:
        raise _unprocessable(
            f"Неизвестный допуск {status_value!r}; допустимые: "
            f"{', '.join(DRIVER_STATUSES)}"
        )
    if categories is None:
        return
    unknown = [code for code in categories if code not in DRIVER_LICENSE_CATEGORIES]
    if unknown:
        raise _unprocessable(
            f"Неизвестные категории {', '.join(repr(c) for c in unknown)}; "
            f"допустимые: {', '.join(DRIVER_LICENSE_CATEGORIES)}"
        )
    if len(set(categories)) != len(categories):
        raise _unprocessable("Категория указана дважды")


def _validate_driver_dates(
    *, experience_since: date | None, license_issued_at: date | None, today: date
) -> None:
    """Стаж и выдача удостоверения — факты о ПРОШЛОМ.

    Дата начала стажа в будущем даёт отрицательный стаж, а «выдано завтра» —
    удостоверение, которого ещё нет. Оба принимать нельзя, иначе сводка
    считает по выдумке.
    """

    if experience_since is not None and experience_since > today:
        raise _unprocessable("Стаж не может начинаться в будущем")
    if license_issued_at is not None and license_issued_at > today:
        raise _unprocessable("Удостоверение не может быть выдано в будущем")


async def _get_driver_or_404(
    session: AsyncSession, tenant: Tenant, driver_id: str
) -> Driver:
    stmt = (
        select(Driver)
        .options(selectinload(Driver.person))
        .where(
            Driver.id == driver_id,
            Driver.tenant_id == tenant.id,
            Driver.deleted_at.is_(None),
        )
    )
    driver = (await session.execute(stmt)).scalar_one_or_none()
    if driver is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="DRIVER_NOT_FOUND",
                message="Driver not found",
                error_type="road_safety",
            ),
        )
    return driver


async def _ensure_person(session: AsyncSession, tenant: Tenant, person_id: str) -> None:
    """Человек обязан быть СВОИМ и живым: карточка водителя не заводит людей."""

    stmt = select(Person.id).where(
        Person.id == person_id,
        Person.tenant_id == tenant.id,
        Person.deleted_at.is_(None),
    )
    if (await session.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="PERSON_NOT_FOUND",
                message="Person not found",
                error_type="road_safety",
            ),
        )


async def _ensure_driver_card_free(
    session: AsyncSession, tenant: Tenant, person_id: str
) -> None:
    """Один человек — одна карточка водителя.

    Вторая запись о том же человеке не заводит второго водителя, она начинает
    расхождение: у одного и того же человека появятся два разных срока
    удостоверения, и какой из них правда — неизвестно.
    """

    stmt = select(Driver.id).where(
        Driver.tenant_id == tenant.id,
        Driver.person_id == person_id,
        Driver.deleted_at.is_(None),
    )
    if (await session.execute(stmt)).scalar_one_or_none() is not None:
        raise _unprocessable("У этого человека уже заведена карточка водителя")


async def _ensure_license_free(
    session: AsyncSession,
    tenant: Tenant,
    license_number: str,
    *,
    exclude_id: str | None = None,
) -> None:
    """Один номер удостоверения — одна карточка: дубль это ошибка ввода."""

    stmt = select(Driver.id).where(
        Driver.tenant_id == tenant.id,
        Driver.license_number == license_number,
        Driver.deleted_at.is_(None),
    )
    if exclude_id:
        stmt = stmt.where(Driver.id != exclude_id)
    if (await session.execute(stmt)).scalar_one_or_none() is not None:
        raise _unprocessable(
            f"Удостоверение {license_number!r} уже внесено другой карточкой"
        )


@router.get("/drivers", response_model=DriverPage)
async def list_drivers(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    status_filter: str | None = Query(default=None, alias="status"),
    category: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> DriverPage:
    """Водительский состав: и допущенные, и отстранённые — история цела."""

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = (
        select(Driver)
        .options(selectinload(Driver.person))
        .where(Driver.tenant_id == tenant.id, Driver.deleted_at.is_(None))
    )
    if status_filter:
        stmt = stmt.where(Driver.status == status_filter)
    stmt = stmt.order_by(Driver.license_number)

    if category:
        # Категория лежит в списке JSON, и одинаково отбирать по нему в SQLite
        # и PostgreSQL нельзя. Расходиться поведением между базами хуже, чем
        # отобрать в приложении: водительский состав измеряется десятками, а
        # не миллионами строк.
        rows = list((await session.execute(stmt)).scalars().all())
        rows = [row for row in rows if category in (row.categories or [])]
        total = len(rows)
        page = rows[offset : offset + limit]
    else:
        total = int(
            await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )
        page = list(
            (await session.execute(stmt.offset(offset).limit(limit))).scalars().all()
        )
    today = date.today()
    return DriverPage(items=[_driver_read(r, today) for r in page], total=total)


@router.post("/drivers", response_model=DriverRead, status_code=status.HTTP_201_CREATED)
async def create_driver(
    request: Request,
    payload: DriverCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> DriverRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    today = date.today()
    _validate_driver_dictionaries(
        categories=payload.categories, status_value=payload.status
    )
    _validate_driver_dates(
        experience_since=payload.experience_since,
        license_issued_at=payload.license_issued_at,
        today=today,
    )
    await _ensure_person(session, tenant, payload.person_id)
    await _ensure_driver_card_free(session, tenant, payload.person_id)
    license_number = payload.license_number.strip().upper()
    await _ensure_license_free(session, tenant, license_number)

    driver = Driver(
        tenant_id=str(tenant.id),
        person_id=payload.person_id,
        license_number=license_number,
        categories=list(payload.categories),
        license_issued_at=payload.license_issued_at,
        license_due=payload.license_due,
        experience_since=payload.experience_since,
        status=payload.status,
        notes=(payload.notes or None),
    )
    session.add(driver)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="Driver",
        object_id=driver.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": driver.id}}},
        details={"entity": "Driver", "person_id": driver.person_id},
    )
    await session.commit()
    return _driver_read(
        await _get_driver_or_404(session, tenant, driver.id), date.today()
    )


@router.patch("/drivers/{driver_id}", response_model=DriverRead)
async def update_driver(
    request: Request,
    driver_id: str,
    payload: DriverUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> DriverRead:
    """Правка карточки. Отстранение — смена ДОПУСКА, а не удаление записи.

    Человека сменить нельзя: карточка принадлежит человеку, и «переписать» её
    на другого значило бы приписать ему чужой стаж и чужое удостоверение.
    Другому человеку заводится своя карточка.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    driver = await _get_driver_or_404(session, tenant, driver_id)
    data = payload.model_dump(exclude_unset=True)
    today = date.today()
    _validate_driver_dictionaries(
        categories=data.get("categories"), status_value=data.get("status")
    )
    _validate_driver_dates(
        experience_since=data.get("experience_since"),
        license_issued_at=data.get("license_issued_at"),
        today=today,
    )
    before = {
        "license_number": driver.license_number,
        "categories": ", ".join(driver.categories or []),
        "status": driver.status,
        "license_due": str(driver.license_due),
        "experience_since": str(driver.experience_since),
    }
    if data.get("license_number"):
        license_number = str(data["license_number"]).strip().upper()
        await _ensure_license_free(
            session, tenant, license_number, exclude_id=driver.id
        )
        driver.license_number = license_number
    if data.get("categories"):
        driver.categories = list(data["categories"])
    if data.get("status"):
        driver.status = str(data["status"])
    for field in ("license_issued_at", "license_due", "experience_since"):
        if field in data:
            setattr(driver, field, data[field])
    if "notes" in data:
        driver.notes = data["notes"] or None
    await session.flush()
    after = {
        "license_number": driver.license_number,
        "categories": ", ".join(driver.categories or []),
        "status": driver.status,
        "license_due": str(driver.license_due),
        "experience_since": str(driver.experience_since),
    }
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="Driver",
        object_id=driver.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "Driver"},
    )
    await session.commit()
    return _driver_read(
        await _get_driver_or_404(session, tenant, driver.id), date.today()
    )


# ---------------------------------------------------------------------------
# Срез-3: путевые листы (Доп. №1 разд. 56.2, пункт «Медицинский и технический
# контроль»).
#
# Лист — ОДНА запись, а не четыре реестра: машина, водитель и три отметки
# контроля сходятся на одном документе. Отдельный «журнал предрейсовых
# осмотров» не заводится — это тот же список листов с отбором по датам, а
# второе хранилище тех же фактов разошлось бы с первым.
# ---------------------------------------------------------------------------

#: отметки, без которых выпуск на линию не подтверждён.
#:
#: ПОСЛЕРЕЙСОВОГО ЗДЕСЬ НЕТ СОЗНАТЕЛЬНО: он обязателен не всем, а перевозчикам
#: пассажиров и опасных грузов, а вида перевозок платформа не знает — та же
#: граница, что у тахографа в срезе-1. Требовать его со всех значило бы
#: показывать нарушение там, где его нет.
_RELEASE_MARKS = ("pre_trip_medical", "pre_trip_technical")


def _release_status(waybill: Waybill) -> str:
    """Вердикт о выпуске — СЧИТАЕТСЯ, а не хранится.

    Сохранённый вердикт разойдётся с отметками при первой же правке: отметку
    поправили, а поле осталось прежним — и какое из двух правда, неизвестно
    (прецедент стажа в срезе-2).
    """

    marks = [getattr(waybill, name) for name in _RELEASE_MARKS]
    if any(mark == "failed" for mark in marks):
        return "blocked"
    if any(mark != "passed" for mark in marks):
        return "unconfirmed"
    return "confirmed"


def _as_utc(value: datetime | None) -> datetime | None:
    """Привести время к сравнимому виду: без пояса — считаем UTC.

    ЗАЧЕМ ЭТО ВООБЩЕ НУЖНО. Колонка объявлена как ``DateTime(timezone=True)``,
    но пояс сохраняет не всякая база: PostgreSQL отдаёт время С поясом, SQLite
    — БЕЗ. Значит в одной и той же правке встречаются оба вида: выезд пришёл
    из базы, возвращение — из запроса. Сравнить их напрямую нельзя, Python
    роняет ``TypeError``.

    Это не теория: лист выписывают утром с выездом, а возвращение проставляют
    вечером отдельной правкой — самое частое действие за смену. Без приведения
    оно отвечало бы пятисоткой (найдено тестом до вливания).
    """

    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _release_condition(value: str):
    """ТО ЖЕ правило выпуска, но выраженное для базы.

    ПОЧЕМУ ДВА ВЫРАЖЕНИЯ ОДНОГО ПРАВИЛА. Вердикт одной записи считает
    ``_release_status``; счётчики сводки и отбор журнала должны считаться в
    базе, иначе тысячи листов за смену пришлось бы тянуть в память ради
    подсчёта. Оба выражения растут из ОДНОГО перечня обязательных отметок
    ``_RELEASE_MARKS``: добавь четвёртую — изменятся оба. Что они дают
    одинаковый ответ, проверяет отдельный тест: без него они молча разойдутся.
    """

    failed = or_(*[getattr(Waybill, mark) == "failed" for mark in _RELEASE_MARKS])
    if value == "blocked":
        return failed
    not_failed = and_(
        *[getattr(Waybill, mark) != "failed" for mark in _RELEASE_MARKS]
    )
    if value == "unconfirmed":
        return and_(
            not_failed,
            or_(
                *[
                    getattr(Waybill, mark) == "not_recorded"
                    for mark in _RELEASE_MARKS
                ]
            ),
        )
    return and_(*[getattr(Waybill, mark) == "passed" for mark in _RELEASE_MARKS])


def _trip_hours(departure: datetime | None, arrival: datetime | None) -> float | None:
    """Время В РЕЙСЕ, а не за рулём.

    Сколько из рейса человек реально вёл машину, платформа не знает: стоянки,
    погрузка и обед в лист не пишутся. Называть эту величину «временем за
    рулём» значило бы соврать в пользу нарушителя.

    Пустая дата — ``None``, а не ноль: «сведений нет» и «рейс длился нисколько»
    это разные утверждения.
    """

    start, end = _as_utc(departure), _as_utc(arrival)
    if start is None or end is None:
        return None
    return round((end - start).total_seconds() / 3600, 2)


def _person_full_name(driver: Driver | None) -> str:
    return _person_name(driver.person if driver else None)


def _waybill_read(waybill: Waybill) -> WaybillRead:
    vehicle = waybill.vehicle
    driver = waybill.driver
    release = _release_status(waybill)
    return WaybillRead(
        id=waybill.id,
        number=waybill.number,
        vehicle_id=waybill.vehicle_id,
        # госномер и ФИО приходят из реестров, в листе они не хранятся —
        # иначе переименование машины оставило бы старое имя в тысяче листов
        vehicle_plate=vehicle.plate_number if vehicle else "",
        vehicle_brand_model=vehicle.brand_model if vehicle else "",
        driver_id=waybill.driver_id,
        driver_name=_person_full_name(driver),
        driver_license_number=driver.license_number if driver else "",
        issued_on=waybill.issued_on,
        departure_at=waybill.departure_at,
        return_at=waybill.return_at,
        trip_hours=_trip_hours(waybill.departure_at, waybill.return_at),
        pre_trip_medical=waybill.pre_trip_medical,
        pre_trip_medical_label=WAYBILL_MARK_STATUSES.get(
            waybill.pre_trip_medical, waybill.pre_trip_medical
        ),
        post_trip_medical=waybill.post_trip_medical,
        post_trip_medical_label=WAYBILL_MARK_STATUSES.get(
            waybill.post_trip_medical, waybill.post_trip_medical
        ),
        pre_trip_technical=waybill.pre_trip_technical,
        pre_trip_technical_label=WAYBILL_MARK_STATUSES.get(
            waybill.pre_trip_technical, waybill.pre_trip_technical
        ),
        release_status=release,
        release_status_label=WAYBILL_RELEASE_TITLES[release],
        status=waybill.status,
        status_label=WAYBILL_STATUSES.get(waybill.status, waybill.status),
        notes=waybill.notes,
    )


def _validate_waybill_dictionaries(
    *,
    status_value: str | None,
    marks: dict[str, str | None],
) -> None:
    if status_value is not None and status_value not in WAYBILL_STATUSES:
        raise _unprocessable(
            f"Неизвестное состояние путевого листа: {status_value!r}. "
            f"Допустимые: {', '.join(WAYBILL_STATUSES)}"
        )
    for field, value in marks.items():
        if value is not None and value not in WAYBILL_MARK_STATUSES:
            raise _unprocessable(
                f"Неизвестное состояние отметки {field!r}: {value!r}. "
                f"Допустимые: {', '.join(WAYBILL_MARK_STATUSES)}"
            )


def _validate_waybill_times(
    departure: datetime | None, arrival: datetime | None
) -> None:
    """Вернуться раньше, чем выехал, нельзя — это опечатка, а не короткий рейс.

    Пропусти её — и время в рейсе станет отрицательным, а журнал за период
    посчитает часы, которых не было.
    """

    start, end = _as_utc(departure), _as_utc(arrival)
    if start is not None and end is not None and end < start:
        raise _unprocessable("Возвращение раньше выезда: проверьте даты рейса")


async def _get_waybill_or_404(
    session: AsyncSession, tenant: Tenant, waybill_id: str
) -> Waybill:
    stmt = (
        select(Waybill)
        .options(
            selectinload(Waybill.vehicle),
            selectinload(Waybill.driver).selectinload(Driver.person),
        )
        .where(
            Waybill.id == waybill_id,
            Waybill.tenant_id == tenant.id,
            Waybill.deleted_at.is_(None),
        )
    )
    waybill = (await session.execute(stmt)).scalar_one_or_none()
    if waybill is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="WAYBILL_NOT_FOUND",
                message="Waybill not found",
                error_type="road_safety",
            ),
        )
    return waybill


async def _ensure_number_free(
    session: AsyncSession,
    tenant: Tenant,
    number: str,
    *,
    exclude_id: str | None = None,
) -> None:
    """Один номер — один лист: дубль это ошибка ввода, а не второй рейс."""

    stmt = select(Waybill.id).where(
        Waybill.tenant_id == tenant.id,
        Waybill.number == number,
        Waybill.deleted_at.is_(None),
    )
    if exclude_id:
        stmt = stmt.where(Waybill.id != exclude_id)
    if (await session.execute(stmt)).scalar_one_or_none() is not None:
        raise _unprocessable(f"Путевой лист {number!r} уже выписан")


async def _resolve_vehicle_for_trip(
    session: AsyncSession, tenant: Tenant, vehicle_id: str
) -> Vehicle:
    """ТС обязано быть СВОИМ и не списанным.

    Запрет на списанную машину — не экспертиза, а целостность: списание уже
    означает «не эксплуатируется», и выписать на неё рейс можно только по
    ошибке. Состояние «не эксплуатируется» (``suspended``) при этом НЕ
    запрещаем: машина может стоять в ремонте и выйти в тот же день.
    """

    vehicle = await _get_vehicle_or_404(session, tenant, vehicle_id)
    if vehicle.status == "decommissioned":
        raise _unprocessable(
            f"ТС {vehicle.plate_number!r} списано: путевой лист на него не выписывается"
        )
    return vehicle


async def _resolve_driver_for_trip(
    session: AsyncSession, tenant: Tenant, driver_id: str
) -> Driver:
    """Водитель обязан быть СВОИМ и допущенным к управлению.

    Отстранённый водитель в рейс не выпускается — ради этого допуск и
    заводился срезом-2. Это тоже целостность, а не экспертиза: платформа не
    решает, ХВАТАЕТ ли водителю категории и стажа, — она лишь не даёт выписать
    лист тому, кого сам арендатор отметил как отстранённого.
    """

    driver = await _get_driver_or_404(session, tenant, driver_id)
    if driver.status != "admitted":
        raise _unprocessable(
            f"Водитель в состоянии {DRIVER_STATUSES.get(driver.status, driver.status)!r}: "
            "путевой лист выписывается только допущенному"
        )
    return driver


@router.get("/waybills", response_model=WaybillPage)
async def list_waybills(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    status_filter: str | None = Query(default=None, alias="status"),
    vehicle_id: str | None = Query(default=None),
    driver_id: str | None = Query(default=None),
    issued_from: date | None = Query(default=None),
    issued_to: date | None = Query(default=None),
    release_status: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> WaybillPage:
    """Реестр листов — он же ЖУРНАЛ за период.

    Отбор по датам и машине и есть журнал предрейсовых осмотров: заводить его
    второй таблицей значило бы получить два списка одних и тех же фактов.
    Порядок — от свежих к старым: журнал читают с последней смены.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = (
        select(Waybill)
        .options(
            selectinload(Waybill.vehicle),
            selectinload(Waybill.driver).selectinload(Driver.person),
        )
        .where(Waybill.tenant_id == tenant.id, Waybill.deleted_at.is_(None))
    )
    if status_filter:
        stmt = stmt.where(Waybill.status == status_filter)
    if vehicle_id:
        stmt = stmt.where(Waybill.vehicle_id == vehicle_id)
    if driver_id:
        stmt = stmt.where(Waybill.driver_id == driver_id)
    if issued_from:
        stmt = stmt.where(Waybill.issued_on >= issued_from)
    if issued_to:
        stmt = stmt.where(Waybill.issued_on <= issued_to)
    stmt = stmt.order_by(Waybill.issued_on.desc(), Waybill.number.desc())

    if release_status:
        if release_status not in WAYBILL_RELEASE_TITLES:
            raise _unprocessable(
                f"Неизвестный вердикт о выпуске: {release_status!r}. "
                f"Допустимые: {', '.join(WAYBILL_RELEASE_TITLES)}"
            )
        # Отбираем В БАЗЕ, а не в памяти: журнал растёт каждую смену, и
        # вытянуть его целиком ради вердикта значило бы уронить экран на
        # арендаторе с большим парком. Правило при этом одно — см.
        # _release_condition.
        stmt = stmt.where(_release_condition(release_status))
    total = int(
        await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )
    page = list(
        (await session.execute(stmt.offset(offset).limit(limit))).scalars().all()
    )
    return WaybillPage(items=[_waybill_read(row) for row in page], total=total)


@router.post(
    "/waybills", response_model=WaybillRead, status_code=status.HTTP_201_CREATED
)
async def create_waybill(
    request: Request,
    payload: WaybillCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> WaybillRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _validate_waybill_dictionaries(
        status_value=payload.status,
        marks={
            "pre_trip_medical": payload.pre_trip_medical,
            "post_trip_medical": payload.post_trip_medical,
            "pre_trip_technical": payload.pre_trip_technical,
        },
    )
    _validate_waybill_times(payload.departure_at, payload.return_at)
    number = payload.number.strip()
    await _ensure_number_free(session, tenant, number)
    vehicle = await _resolve_vehicle_for_trip(session, tenant, payload.vehicle_id)
    driver = await _resolve_driver_for_trip(session, tenant, payload.driver_id)

    waybill = Waybill(
        tenant_id=str(tenant.id),
        number=number,
        vehicle_id=vehicle.id,
        driver_id=driver.id,
        issued_on=payload.issued_on,
        departure_at=payload.departure_at,
        return_at=payload.return_at,
        pre_trip_medical=payload.pre_trip_medical,
        post_trip_medical=payload.post_trip_medical,
        pre_trip_technical=payload.pre_trip_technical,
        status=payload.status,
        notes=(payload.notes or None),
    )
    session.add(waybill)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="Waybill",
        object_id=waybill.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": waybill.id}}},
        details={
            "entity": "Waybill",
            "number": waybill.number,
            "vehicle_id": waybill.vehicle_id,
            "driver_id": waybill.driver_id,
        },
    )
    await session.commit()
    return _waybill_read(await _get_waybill_or_404(session, tenant, waybill.id))


@router.patch("/waybills/{waybill_id}", response_model=WaybillRead)
async def update_waybill(
    request: Request,
    waybill_id: str,
    payload: WaybillUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> WaybillRead:
    """Правка листа: отметки контроля, время рейса, аннулирование.

    МАШИНУ И ВОДИТЕЛЯ СМЕНИТЬ НЕЛЬЗЯ — полей для этого нет. Другая машина или
    другой водитель это ДРУГОЙ РЕЙС, и переписать на него старый лист значило
    бы приписать чужому рейсу чужие отметки медосмотра. Ошибочный лист
    аннулируется, а верный выписывается заново.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    waybill = await _get_waybill_or_404(session, tenant, waybill_id)
    data = payload.model_dump(exclude_unset=True)
    _validate_waybill_dictionaries(
        status_value=data.get("status"),
        marks={
            field: data.get(field)
            for field in (
                "pre_trip_medical",
                "post_trip_medical",
                "pre_trip_technical",
            )
        },
    )
    departure = data.get("departure_at", waybill.departure_at)
    arrival = data.get("return_at", waybill.return_at)
    _validate_waybill_times(departure, arrival)

    before = {
        "number": waybill.number,
        "status": waybill.status,
        "pre_trip_medical": waybill.pre_trip_medical,
        "post_trip_medical": waybill.post_trip_medical,
        "pre_trip_technical": waybill.pre_trip_technical,
        "release_status": _release_status(waybill),
    }
    if data.get("number"):
        number = str(data["number"]).strip()
        await _ensure_number_free(session, tenant, number, exclude_id=waybill.id)
        waybill.number = number
    for field in (
        "issued_on",
        "departure_at",
        "return_at",
        "pre_trip_medical",
        "post_trip_medical",
        "pre_trip_technical",
        "status",
    ):
        if data.get(field) is not None:
            setattr(waybill, field, data[field])
        elif field in data and field in ("departure_at", "return_at"):
            # снять время рейса можно: внесли по ошибке — стирается в
            # «сведений нет», а не остаётся навсегда
            setattr(waybill, field, None)
    if "notes" in data:
        waybill.notes = data["notes"] or None
    await session.flush()
    after = {
        "number": waybill.number,
        "status": waybill.status,
        "pre_trip_medical": waybill.pre_trip_medical,
        "post_trip_medical": waybill.post_trip_medical,
        "pre_trip_technical": waybill.pre_trip_technical,
        "release_status": _release_status(waybill),
    }
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="Waybill",
        object_id=waybill.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "Waybill"},
    )
    await session.commit()
    return _waybill_read(await _get_waybill_or_404(session, tenant, waybill.id))


# ---------------------------------------------------------------------------
# Срез-4: учёт ДТП (Доп. №1 разд. 56.2, пункт «Профилактика и учёт ДТП»).
#
# ТЗ требует «связь с инцидентами и CAPA» — именно СВЯЗЬ. Ядровой инцидент
# здесь НЕ поглощается: он требует площадку (у ДТП на трассе её нет), его вид
# — перечисление в базе, общее для всего продукта, и помятый бампер это ДТП,
# но не происшествие по охране труда. Мероприятия живут в ядровом CAPA, куда
# ДТП адресуется парой «тип источника + идентификатор».
# ---------------------------------------------------------------------------

#: мероприятие считается НЕЗАКРЫТЫМ только в состоянии ``open``. Остальные
#: (``done``/``verified``/``closed``/``canceled``) висящей работой не являются.
_CAPA_OPEN_STATUS = "open"


def _consequences(accident: RoadAccident) -> str:
    """Тяжесть СЧИТАЕТСЯ из чисел людей, а не хранится словом.

    Сохранённая «тяжесть» разойдётся с числами при первом же уточнении: в
    сводке ГИБДД пострадавших стало двое, число поправили, а слово осталось
    прежним — и какое из двух правда, непонятно.
    """

    if accident.fatalities_count > 0:
        return "fatal"
    if accident.injured_count > 0:
        return "injured"
    return "damage_only"


def _follow_up(*, capa_total: int, capa_open: int, incident_id: str | None) -> str:
    """Состояние разбора СЛЕДУЕТ ИЗ СВЯЗЕЙ — своего статуса у ДТП нет.

    Заведи ДТП собственную галочку «разобрано» — она разошлась бы с
    мероприятиями в первый же день: мероприятие закрыли, а галочку не
    переставили. Поэтому состояние выводится из ядровых мероприятий и ссылки
    на расследование.

    ГРАНИЦА: это факт о НЕЗАКРЫТЫХ мероприятиях, а не оценка «разобрано
    хорошо». Достаточны ли мероприятия, платформа не решает.
    """

    if capa_total == 0 and incident_id is None:
        return "not_started"
    if capa_open > 0:
        return "open"
    return "closed"


async def _capa_counts(
    session: AsyncSession, tenant: Tenant, accident_ids: list[str]
) -> dict[str, tuple[int, int]]:
    """Счёт мероприятий по ДТП — ОДНИМ запросом на страницу.

    Спрашивать ядро по одному мероприятию на строку значило бы завести N+1 на
    экране, который открывают каждый день.
    """

    if not accident_ids:
        return {}
    rows = (
        await session.execute(
            select(
                CorrectiveAction.source_id,
                func.count(),
                func.sum(
                    case(
                        (CorrectiveAction.status == _CAPA_OPEN_STATUS, 1),
                        else_=0,
                    )
                ),
            )
            .where(
                CorrectiveAction.tenant_id == tenant.id,
                CorrectiveAction.deleted_at.is_(None),
                CorrectiveAction.source_type == ACCIDENT_CAPA_SOURCE,
                CorrectiveAction.source_id.in_(accident_ids),
            )
            .group_by(CorrectiveAction.source_id)
        )
    ).all()
    return {str(sid): (int(total or 0), int(open_ or 0)) for sid, total, open_ in rows}


def _accident_read(
    accident: RoadAccident, counts: dict[str, tuple[int, int]]
) -> RoadAccidentRead:
    capa_total, capa_open = counts.get(accident.id, (0, 0))
    consequences = _consequences(accident)
    follow_up = _follow_up(
        capa_total=capa_total,
        capa_open=capa_open,
        incident_id=accident.incident_id,
    )
    driver = accident.driver
    return RoadAccidentRead(
        id=accident.id,
        occurred_at=accident.occurred_at,
        place=accident.place,
        vehicle_id=accident.vehicle_id,
        # госномер из реестра: в записи о ДТП он не хранится
        vehicle_plate=accident.vehicle.plate_number if accident.vehicle else "",
        driver_id=accident.driver_id,
        driver_name=_person_name(driver.person) if driver else None,
        kind=accident.kind,
        kind_label=ACCIDENT_KINDS.get(accident.kind, accident.kind),
        injured_count=accident.injured_count,
        fatalities_count=accident.fatalities_count,
        consequences=consequences,
        consequences_label=ACCIDENT_CONSEQUENCE_TITLES[consequences],
        fault=accident.fault,
        fault_label=ACCIDENT_FAULT.get(accident.fault, accident.fault),
        gibdd_reference=accident.gibdd_reference,
        incident_id=accident.incident_id,
        description=accident.description,
        capa_total=capa_total,
        capa_open=capa_open,
        follow_up=follow_up,
        follow_up_label=ACCIDENT_FOLLOWUP_TITLES[follow_up],
    )


def _validate_accident_dictionaries(
    *, kind: str | None, fault: str | None
) -> None:
    if kind is not None and kind not in ACCIDENT_KINDS:
        raise _unprocessable(
            f"Неизвестный вид ДТП: {kind!r}. Допустимые: {', '.join(ACCIDENT_KINDS)}"
        )
    if fault is not None and fault not in ACCIDENT_FAULT:
        raise _unprocessable(
            f"Неизвестное значение вины: {fault!r}. "
            f"Допустимые: {', '.join(ACCIDENT_FAULT)}"
        )


def _validate_occurred_at(occurred_at: datetime | None) -> None:
    """ДТП в будущем не бывает — это опечатка в дате, а не запись наперёд."""

    moment = _as_utc(occurred_at)
    if moment is not None and moment > datetime.now(timezone.utc):
        raise _unprocessable("ДТП не может произойти в будущем: проверьте дату")


async def _get_accident_or_404(
    session: AsyncSession, tenant: Tenant, accident_id: str
) -> RoadAccident:
    stmt = (
        select(RoadAccident)
        .options(
            selectinload(RoadAccident.vehicle),
            selectinload(RoadAccident.driver).selectinload(Driver.person),
        )
        .where(
            RoadAccident.id == accident_id,
            RoadAccident.tenant_id == tenant.id,
            RoadAccident.deleted_at.is_(None),
        )
    )
    accident = (await session.execute(stmt)).scalar_one_or_none()
    if accident is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="ACCIDENT_NOT_FOUND",
                message="Road accident not found",
                error_type="road_safety",
            ),
        )
    return accident


async def _ensure_incident(
    session: AsyncSession, tenant: Tenant, incident_id: str
) -> None:
    """Расследование обязано быть СВОИМ: контур БДД инцидентов не заводит."""

    stmt = select(Incident.id).where(
        Incident.id == incident_id,
        Incident.tenant_id == tenant.id,
        Incident.deleted_at.is_(None),
    )
    if (await session.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="INCIDENT_NOT_FOUND",
                message="Incident not found",
                error_type="road_safety",
            ),
        )


@router.get("/accidents", response_model=RoadAccidentPage)
async def list_accidents(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    vehicle_id: str | None = Query(default=None),
    driver_id: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    fault: str | None = Query(default=None),
    occurred_from: datetime | None = Query(default=None),
    occurred_to: datetime | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> RoadAccidentPage:
    """Реестр ДТП. Порядок — от свежих: разбирают последнее происшествие."""

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = (
        select(RoadAccident)
        .options(
            selectinload(RoadAccident.vehicle),
            selectinload(RoadAccident.driver).selectinload(Driver.person),
        )
        .where(
            RoadAccident.tenant_id == tenant.id, RoadAccident.deleted_at.is_(None)
        )
    )
    if vehicle_id:
        stmt = stmt.where(RoadAccident.vehicle_id == vehicle_id)
    if driver_id:
        stmt = stmt.where(RoadAccident.driver_id == driver_id)
    if kind:
        stmt = stmt.where(RoadAccident.kind == kind)
    if fault:
        stmt = stmt.where(RoadAccident.fault == fault)
    if occurred_from:
        stmt = stmt.where(RoadAccident.occurred_at >= occurred_from)
    if occurred_to:
        stmt = stmt.where(RoadAccident.occurred_at <= occurred_to)
    stmt = stmt.order_by(RoadAccident.occurred_at.desc())

    total = int(
        await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )
    page = list(
        (await session.execute(stmt.offset(offset).limit(limit))).scalars().all()
    )
    counts = await _capa_counts(session, tenant, [row.id for row in page])
    return RoadAccidentPage(
        items=[_accident_read(row, counts) for row in page], total=total
    )


@router.post(
    "/accidents", response_model=RoadAccidentRead, status_code=status.HTTP_201_CREATED
)
async def create_accident(
    request: Request,
    payload: RoadAccidentCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> RoadAccidentRead:
    """Регистрация ДТП.

    СПИСАННОЕ ТС И ОТСТРАНЁННЫЙ ВОДИТЕЛЬ ЗДЕСЬ РАЗРЕШЕНЫ — в ОТЛИЧИЕ от
    путевого листа, и это не недосмотр. Лист выписывают наперёд, поэтому на
    списанную машину его выписать нельзя. ДТП же регистрируют ЗАДНИМ ЧИСЛОМ:
    машину могли списать после аварии, а водителя — отстранить ИЗ-ЗА неё.
    Запретить это значило бы сделать невозможной запись самых тяжёлых случаев.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    _validate_accident_dictionaries(kind=payload.kind, fault=payload.fault)
    _validate_occurred_at(payload.occurred_at)
    vehicle = await _get_vehicle_or_404(session, tenant, payload.vehicle_id)
    if payload.driver_id:
        await _get_driver_or_404(session, tenant, payload.driver_id)
    if payload.incident_id:
        await _ensure_incident(session, tenant, payload.incident_id)

    accident = RoadAccident(
        tenant_id=str(tenant.id),
        occurred_at=payload.occurred_at,
        place=payload.place.strip(),
        vehicle_id=vehicle.id,
        driver_id=payload.driver_id or None,
        kind=payload.kind,
        injured_count=payload.injured_count,
        fatalities_count=payload.fatalities_count,
        fault=payload.fault,
        gibdd_reference=(payload.gibdd_reference or None),
        incident_id=payload.incident_id or None,
        description=(payload.description or None),
    )
    session.add(accident)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="RoadAccident",
        object_id=accident.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": accident.id}}},
        details={
            "entity": "RoadAccident",
            "vehicle_id": accident.vehicle_id,
            "kind": accident.kind,
        },
    )
    await session.commit()
    fresh = await _get_accident_or_404(session, tenant, accident.id)
    return _accident_read(fresh, await _capa_counts(session, tenant, [fresh.id]))


@router.patch("/accidents/{accident_id}", response_model=RoadAccidentRead)
async def update_accident(
    request: Request,
    accident_id: str,
    payload: RoadAccidentUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> RoadAccidentRead:
    """Правка: уточнение обстоятельств, вины по документам и связей.

    МАШИНУ СМЕНИТЬ НЕЛЬЗЯ — поля для этого нет: другая машина это другое ДТП.
    Водителя же уточнить МОЖНО: кто был за рулём, выясняется не всегда сразу.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    accident = await _get_accident_or_404(session, tenant, accident_id)
    data = payload.model_dump(exclude_unset=True)
    _validate_accident_dictionaries(kind=data.get("kind"), fault=data.get("fault"))
    _validate_occurred_at(data.get("occurred_at"))
    if data.get("driver_id"):
        await _get_driver_or_404(session, tenant, str(data["driver_id"]))
    if data.get("incident_id"):
        await _ensure_incident(session, tenant, str(data["incident_id"]))

    before = {
        "kind": accident.kind,
        "fault": accident.fault,
        "injured_count": str(accident.injured_count),
        "fatalities_count": str(accident.fatalities_count),
        "incident_id": str(accident.incident_id),
        "consequences": _consequences(accident),
    }
    for field in (
        "occurred_at",
        "place",
        "kind",
        "fault",
        "injured_count",
        "fatalities_count",
    ):
        if data.get(field) is not None:
            setattr(accident, field, data[field])
    # снять связь и водителя МОЖНО: ошибочную привязку надо уметь отменить,
    # иначе она останется навсегда
    for field in ("driver_id", "incident_id", "gibdd_reference", "description"):
        if field in data:
            setattr(accident, field, data[field] or None)
    await session.flush()
    after = {
        "kind": accident.kind,
        "fault": accident.fault,
        "injured_count": str(accident.injured_count),
        "fatalities_count": str(accident.fatalities_count),
        "incident_id": str(accident.incident_id),
        "consequences": _consequences(accident),
    }
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="RoadAccident",
        object_id=accident.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "RoadAccident"},
    )
    await session.commit()
    fresh = await _get_accident_or_404(session, tenant, accident.id)
    return _accident_read(fresh, await _capa_counts(session, tenant, [fresh.id]))
