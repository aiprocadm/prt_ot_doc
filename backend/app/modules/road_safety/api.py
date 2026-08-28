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

from app.api.dependencies import get_session, get_tenant_record
from app.core.errors import api_problem_detail
from app.core.feature_flags import is_module_enabled, raise_for_disabled_module
from app.core.security import AccessContext, abac, rbac
from app.core.tenant_validation import TenantContextValidator
from app.models.master_data import Site
from app.models.models import Tenant
from app.models.road_safety import (
    TACHOGRAPH_STATUS_TITLES,
    VEHICLE_DOC_STATUS_TITLES,
    VEHICLE_KINDS,
    VEHICLE_STATUSES,
    Vehicle,
)
from app.schemas.road_safety import (
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
    """Сводка парка: состояния и сроки.

    Просрочки считаются ТОЛЬКО по ТС в эксплуатации: у списанной машины
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
    )
