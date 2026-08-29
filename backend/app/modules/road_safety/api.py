"""Контур БДД, собственные ручки (Доп. №1 разд. 56.2, срез-1).

Реестр транспортных средств: учёт парка, сроки диагностической карты, полиса
и поверки тахографа. До этого среза по разд. 56.2 не было ни одной модели
транспорта — ТЗ отсылало к «transport safety (vNext §17.3)», которого в коде
не существовало.

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
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_session, get_tenant_record
from app.core.errors import api_problem_detail
from app.core.feature_flags import is_module_enabled, raise_for_disabled_module
from app.core.security import AccessContext, abac, rbac
from app.core.tenant_validation import TenantContextValidator
from app.models.master_data import Person, Site
from app.models.models import Tenant
from app.models.road_safety import (
    DRIVER_LICENSE_CATEGORIES,
    DRIVER_STATUSES,
    TACHOGRAPH_STATUS_TITLES,
    VEHICLE_DOC_STATUS_TITLES,
    VEHICLE_KINDS,
    VEHICLE_STATUSES,
    Driver,
    Vehicle,
)
from app.schemas.road_safety import (
    DriverCreate,
    DriverPage,
    DriverRead,
    DriverUpdate,
    RoadSafetyReadinessRead,
    VehicleCreate,
    VehiclePage,
    VehicleRead,
    VehicleUpdate,
)
from app.services.audit import AuditService, field_level_diff

router = APIRouter(prefix="/road-safety", tags=["road-safety"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_ROLES = ["admin", "owner", "ot_pb_lead", "ot_specialist"]

#: горизонт «скоро истекает» — тот же, что у остальных сводок продукта
_DUE_SOON_DAYS = 30


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
    """Сводка БДД: парк, водительский состав и сроки.

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
