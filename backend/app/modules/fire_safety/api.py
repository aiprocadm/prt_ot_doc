"""Контур ПБ, собственные ручки (Доп. №1 разд. 54.1, срез-1).

Первичные средства пожаротушения и системы защиты (АУПС/АУПТ/СОУЭ) с
регламентными сроками — перезарядка и поверка/ТО. Просрочки этих сроков —
первое, что смотрит инспектор МЧС; сводка ``/fire-safety/readiness`` отвечает
на этот вопрос одним запросом.

До этого среза у дисциплины НЕ БЫЛО своих ручек — три экрана-сводки собирались
из общих (площадки, проверки, задачи), и модуль ``fire_safety`` числился в
``MODULES_WITHOUT_BACKEND_GATE`` с причиной «появится собственный роутер —
гейт обязателен». Роутер появился — гейт роутерный, на каждом роуте по
построению (разд. 61.3), аутентификация раньше гейта, отключённый (но
выдававшийся) модуль читается (read-only, BIZ-61 срез-6).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.disciplines import BRIEFING_TYPE_DISCIPLINE, Discipline
from app.core.errors import api_problem_detail
from app.core.feature_flags import is_module_enabled, raise_for_disabled_module
from app.core.security import AccessContext, abac, rbac
from app.core.tenant_validation import TenantContextValidator
from app.models.briefings import BriefingEntry
from app.models.fire_safety import (
    FIRE_DOCUMENT_KINDS,
    FIRE_DOCUMENT_STATUS_TITLES,
    FIRE_DRILL_KINDS,
    FIRE_DRILL_OUTCOMES,
    FIRE_EQUIPMENT_KINDS,
    FIRE_MAINTENANCE_DUE_FIELD,
    FIRE_MAINTENANCE_KINDS,
    FIRE_MAINTENANCE_PASSING_RESULTS,
    FIRE_MAINTENANCE_RESULTS,
    FireDrill,
    FireMaintenanceRecord,
    FireSafetyDocument,
    FireSafetyEquipment,
)
from app.models.master_data import Site
from app.models.models import Tenant
from app.schemas.fire_safety import (
    FireDocumentCreate,
    FireDocumentPage,
    FireDocumentRead,
    FireDocumentUpdate,
    FireDrillCreate,
    FireDrillPage,
    FireDrillRead,
    FireDrillUpdate,
    FireEquipmentCreate,
    FireEquipmentPage,
    FireEquipmentRead,
    FireEquipmentUpdate,
    FireMaintenanceCreate,
    FireMaintenancePage,
    FireMaintenanceRead,
    FireReadinessRead,
)
from app.services.audit import AuditService, field_level_diff
from app.services.discipline_incidents import open_incidents_count

router = APIRouter(prefix="/fire-safety", tags=["fire-safety"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_ROLES = ["admin", "owner", "ot_pb_lead", "ot_specialist"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


Access = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_ROLES, action="manage fire safety")),
]

_FEATURE_CODE = "fire_safety"

#: горизонт «скоро истекает» для сводки готовности
_DUE_SOON_DAYS = 30


async def _require_fire_safety(
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
            error_type="fire_safety",
            disabled_code="FIRE_SAFETY_DISABLED",
            disabled_message="Fire safety module is not enabled for this tenant",
        )


router.dependencies.append(Depends(_require_fire_safety))


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(
            code="FIRE_EQUIPMENT_VALIDATION_ERROR", message=message, error_type="fire_safety"
        ),
    )


async def _get_unit_or_404(
    session: AsyncSession, tenant: Tenant, unit_id: str
) -> FireSafetyEquipment:
    stmt = select(FireSafetyEquipment).where(
        FireSafetyEquipment.id == unit_id,
        FireSafetyEquipment.tenant_id == tenant.id,
        FireSafetyEquipment.deleted_at.is_(None),
    )
    unit = (await session.execute(stmt)).scalar_one_or_none()
    if unit is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="FIRE_EQUIPMENT_NOT_FOUND",
                message="Fire safety equipment not found",
                error_type="fire_safety",
            ),
        )
    return unit


async def _validate_payload(
    session: AsyncSession, tenant: Tenant, *, kind: str | None, site_id: str | None
) -> None:
    if kind is not None and kind not in FIRE_EQUIPMENT_KINDS:
        raise _unprocessable(
            f"Неизвестный вид средства {kind!r}; допустимые: {', '.join(FIRE_EQUIPMENT_KINDS)}"
        )
    if site_id:
        stmt = select(Site.id).where(
            Site.id == site_id,
            Site.tenant_id == tenant.id,
            Site.deleted_at.is_(None),
        )
        if (await session.execute(stmt)).scalar_one_or_none() is None:
            raise _unprocessable("Площадка не найдена")


async def _last_maintenance_map(
    session: AsyncSession, tenant: Tenant, unit_ids: list[str]
) -> dict[str, tuple[date, str]]:
    """Последняя работа по каждому средству — одним запросом, а не N+1.

    «Последняя» — по ДАТЕ РАБОТЫ, а не по порядку внесения: задним числом
    вносят чаще, чем кажется, и «последней» тогда оказалась бы позавчерашняя
    запись, внесённая сегодня.
    """

    if not unit_ids:
        return {}
    ranked = (
        select(
            FireMaintenanceRecord.equipment_id.label("equipment_id"),
            FireMaintenanceRecord.performed_on.label("performed_on"),
            FireMaintenanceRecord.result.label("result"),
            func.row_number()
            .over(
                partition_by=FireMaintenanceRecord.equipment_id,
                order_by=(
                    FireMaintenanceRecord.performed_on.desc(),
                    FireMaintenanceRecord.created_at.desc(),
                ),
            )
            .label("rn"),
        )
        .where(
            FireMaintenanceRecord.tenant_id == tenant.id,
            FireMaintenanceRecord.deleted_at.is_(None),
            FireMaintenanceRecord.equipment_id.in_(unit_ids),
        )
        .subquery()
    )
    rows = await session.execute(
        select(ranked.c.equipment_id, ranked.c.performed_on, ranked.c.result).where(
            ranked.c.rn == 1
        )
    )
    return {row.equipment_id: (row.performed_on, row.result) for row in rows}


def _equipment_read(
    unit: FireSafetyEquipment, last: tuple[date, str] | None
) -> FireEquipmentRead:
    return FireEquipmentRead(
        id=unit.id,
        kind=unit.kind,
        label=unit.label,
        site_id=unit.site_id,
        location=unit.location,
        recharge_due=unit.recharge_due,
        inspection_due=unit.inspection_due,
        status=unit.status,
        last_maintenance_on=last[0] if last else None,
        last_maintenance_result=last[1] if last else None,
    )


@router.get("/equipment", response_model=FireEquipmentPage)
async def list_equipment(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    kind: str | None = Query(default=None),
    site_id: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> FireEquipmentPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(FireSafetyEquipment).where(
        FireSafetyEquipment.tenant_id == tenant.id,
        FireSafetyEquipment.deleted_at.is_(None),
    )
    if kind:
        stmt = stmt.where(FireSafetyEquipment.kind == kind)
    if site_id:
        stmt = stmt.where(FireSafetyEquipment.site_id == site_id)
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        (
            await session.execute(
                stmt.order_by(FireSafetyEquipment.created_at.desc()).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    last_map = await _last_maintenance_map(session, tenant, [r.id for r in rows])
    return FireEquipmentPage(
        items=[_equipment_read(r, last_map.get(r.id)) for r in rows], total=total
    )


@router.post("/equipment", response_model=FireEquipmentRead, status_code=status.HTTP_201_CREATED)
async def create_equipment(
    request: Request,
    payload: FireEquipmentCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> FireEquipmentRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _validate_payload(session, tenant, kind=payload.kind, site_id=payload.site_id)
    unit = FireSafetyEquipment(
        tenant_id=str(tenant.id),
        kind=payload.kind,
        label=payload.label.strip(),
        site_id=payload.site_id,
        location=(payload.location or None),
        recharge_due=payload.recharge_due,
        inspection_due=payload.inspection_due,
        status=payload.status or "active",
    )
    session.add(unit)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="FireSafetyEquipment",
        object_id=unit.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": unit.id}}},
        details={"entity": "FireSafetyEquipment", "kind": unit.kind},
    )
    await session.commit()
    await session.refresh(unit)
    return FireEquipmentRead.model_validate(unit)


@router.patch("/equipment/{unit_id}", response_model=FireEquipmentRead)
async def update_equipment(
    request: Request,
    unit_id: str,
    payload: FireEquipmentUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> FireEquipmentRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    unit = await _get_unit_or_404(session, tenant, unit_id)
    data = payload.model_dump(exclude_unset=True)
    await _validate_payload(
        session, tenant, kind=data.get("kind"), site_id=data.get("site_id")
    )
    before = FireEquipmentRead.model_validate(unit).model_dump()
    for field in ("kind", "label", "site_id", "location", "recharge_due", "inspection_due"):
        if field in data:
            value = data[field]
            if field == "label" and (value is None or not str(value).strip()):
                raise _unprocessable("label cannot be empty")
            setattr(unit, field, value.strip() if isinstance(value, str) else value)
    if "status" in data:
        unit.status = (data["status"] or "active").strip() or "active"
    after = FireEquipmentRead.model_validate(unit).model_dump()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="FireSafetyEquipment",
        object_id=unit.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "FireSafetyEquipment"},
    )
    await session.commit()
    await session.refresh(unit)
    return FireEquipmentRead.model_validate(unit)


def _document_status(review_due: date | None, today: date) -> str:
    """Состояние документа: ok / due_soon / overdue — считается ПРИ ЧТЕНИИ.

    СЛОВАРЬ ЗНАЧЕНИЙ — ядровой (``app.domains.shared.ContingentItemStatus``),
    а вот ИМПОРТИРОВАТЬ его отсюда нельзя: гард границ контекстов (ARCH-3)
    запрещает ``app.modules.* -> app.domains.*``, и три таких импорта у
    подрядчиков и СИЗ числятся в списке ДОЛГА, а не образцом. Заводить
    четвёртую запись долга ради четырёх строк — плохой размен; переезд общего
    ядра сроков объявлен отдельным срезом в самом гарде. Правило совпадает с
    ядровым дословно, включая горизонт «скоро» — тот же, что у остальной
    готовности к проверке.

    Отличие от ядрового ``classify`` названо явно: там пустая дата означает
    MISSING, а здесь пустой срок пересмотра означает БЕССРОЧНЫЙ — приказ без
    даты пересмотра не «отсутствующий документ», он есть и лежит в реестре
    (тот же выбор сделан у документов подрядчиков).
    """

    if review_due is None:
        return "ok"
    if review_due < today:
        return "overdue"
    if review_due <= today + timedelta(days=_DUE_SOON_DAYS):
        return "due_soon"
    return "ok"


def _fire_document_read(doc: FireSafetyDocument, today: date) -> FireDocumentRead:
    status_value = _document_status(doc.review_due, today)
    return FireDocumentRead(
        id=doc.id,
        kind=doc.kind,
        kind_label=FIRE_DOCUMENT_KINDS.get(doc.kind, doc.kind),
        title=doc.title,
        site_id=doc.site_id,
        number=doc.number,
        location=doc.location,
        approved_on=doc.approved_on,
        review_due=doc.review_due,
        responsible=doc.responsible,
        document_id=doc.document_id,
        notes=doc.notes,
        status=status_value,
        status_label=FIRE_DOCUMENT_STATUS_TITLES.get(status_value, status_value),
    )


async def _get_fire_document_or_404(
    session: AsyncSession, tenant: Tenant, document_id: str
) -> FireSafetyDocument:
    stmt = select(FireSafetyDocument).where(
        FireSafetyDocument.id == document_id,
        FireSafetyDocument.tenant_id == tenant.id,
        FireSafetyDocument.deleted_at.is_(None),
    )
    doc = (await session.execute(stmt)).scalar_one_or_none()
    if doc is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="FIRE_DOCUMENT_NOT_FOUND",
                message="Fire safety document not found",
                error_type="fire_safety",
            ),
        )
    return doc


@router.get("/documents", response_model=FireDocumentPage)
async def list_fire_documents(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    kind: str | None = Query(default=None),
    site_id: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> FireDocumentPage:
    """Какие документы ПБ у объекта есть и не пора ли их пересматривать."""

    TenantContextValidator.ensure_tenant_context(tenant)
    today = date.today()
    stmt = select(FireSafetyDocument).where(
        FireSafetyDocument.tenant_id == tenant.id,
        FireSafetyDocument.deleted_at.is_(None),
    )
    if kind:
        stmt = stmt.where(FireSafetyDocument.kind == kind)
    if site_id:
        stmt = stmt.where(FireSafetyDocument.site_id == site_id)
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        (
            await session.execute(
                stmt.order_by(FireSafetyDocument.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return FireDocumentPage(
        items=[_fire_document_read(r, today) for r in rows], total=total
    )


@router.post(
    "/documents", response_model=FireDocumentRead, status_code=status.HTTP_201_CREATED
)
async def create_fire_document(
    request: Request,
    payload: FireDocumentCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> FireDocumentRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _validate_payload(session, tenant, kind=None, site_id=payload.site_id)
    if payload.kind not in FIRE_DOCUMENT_KINDS:
        raise _unprocessable(
            f"Неизвестный вид документа {payload.kind!r}; допустимые: "
            f"{', '.join(FIRE_DOCUMENT_KINDS)}"
        )
    doc = FireSafetyDocument(
        tenant_id=str(tenant.id),
        kind=payload.kind,
        title=payload.title.strip(),
        site_id=payload.site_id,
        number=(payload.number or None),
        location=(payload.location or None),
        approved_on=payload.approved_on,
        review_due=payload.review_due,
        responsible=(payload.responsible or None),
        document_id=payload.document_id,
        notes=(payload.notes or None),
    )
    session.add(doc)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="FireSafetyDocument",
        object_id=doc.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": doc.id}}},
        details={"entity": "FireSafetyDocument", "kind": doc.kind},
    )
    await session.commit()
    await session.refresh(doc)
    return _fire_document_read(doc, date.today())


@router.patch("/documents/{document_id}", response_model=FireDocumentRead)
async def update_fire_document(
    request: Request,
    document_id: str,
    payload: FireDocumentUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> FireDocumentRead:
    """Пересмотрели документ → переносится срок; заменили — правится карточка."""

    TenantContextValidator.ensure_tenant_context(tenant)
    doc = await _get_fire_document_or_404(session, tenant, document_id)
    data = payload.model_dump(exclude_unset=True)
    await _validate_payload(session, tenant, kind=None, site_id=data.get("site_id"))
    if "kind" in data and data["kind"] not in FIRE_DOCUMENT_KINDS:
        raise _unprocessable(
            f"Неизвестный вид документа {data['kind']!r}; допустимые: "
            f"{', '.join(FIRE_DOCUMENT_KINDS)}"
        )
    before = _fire_document_read(doc, date.today()).model_dump()
    for field in (
        "kind",
        "title",
        "site_id",
        "number",
        "location",
        "approved_on",
        "review_due",
        "responsible",
        "document_id",
        "notes",
    ):
        if field in data:
            value = data[field]
            if field == "title" and (value is None or not str(value).strip()):
                raise _unprocessable("title cannot be empty")
            setattr(doc, field, value.strip() if isinstance(value, str) else value)
    after = _fire_document_read(doc, date.today()).model_dump()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="FireSafetyDocument",
        object_id=doc.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "FireSafetyDocument"},
    )
    await session.commit()
    await session.refresh(doc)
    return _fire_document_read(doc, date.today())


def _maintenance_read(record: FireMaintenanceRecord, *, shifted: bool) -> FireMaintenanceRead:
    return FireMaintenanceRead(
        id=record.id,
        equipment_id=record.equipment_id,
        kind=record.kind,
        kind_label=FIRE_MAINTENANCE_KINDS.get(record.kind, record.kind),
        performed_on=record.performed_on,
        result=record.result,
        result_label=FIRE_MAINTENANCE_RESULTS.get(record.result, record.result),
        performer=record.performer,
        notes=record.notes,
        next_due=record.next_due,
        shifted_due=shifted,
    )


@router.get("/maintenance", response_model=FireMaintenancePage)
async def list_maintenance(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    equipment_id: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> FireMaintenancePage:
    """История работ: то самое доказательство, которого не было до среза."""

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(FireMaintenanceRecord).where(
        FireMaintenanceRecord.tenant_id == tenant.id,
        FireMaintenanceRecord.deleted_at.is_(None),
    )
    if equipment_id:
        stmt = stmt.where(FireMaintenanceRecord.equipment_id == equipment_id)
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        (
            await session.execute(
                stmt.order_by(
                    FireMaintenanceRecord.performed_on.desc(),
                    FireMaintenanceRecord.created_at.desc(),
                )
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return FireMaintenancePage(
        items=[
            _maintenance_read(
                r,
                shifted=r.next_due is not None
                and r.result in FIRE_MAINTENANCE_PASSING_RESULTS,
            )
            for r in rows
        ],
        total=total,
    )


@router.post(
    "/maintenance", response_model=FireMaintenanceRead, status_code=status.HTTP_201_CREATED
)
async def record_maintenance(
    request: Request,
    payload: FireMaintenanceCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> FireMaintenanceRead:
    """Запись о выполненной работе — и ЕДИНСТВЕННЫЙ обоснованный перенос срока.

    Срок у средства двигает сама работа: до этого среза срок можно было
    сдвинуть голой правкой поля, и «ТО проведено» ничем не отличалось от
    «ТО не проводили, но дату поправили».
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    unit = await _get_unit_or_404(session, tenant, payload.equipment_id)
    if payload.kind not in FIRE_MAINTENANCE_KINDS:
        raise _unprocessable(
            f"Неизвестный вид работы {payload.kind!r}; допустимые: "
            f"{', '.join(FIRE_MAINTENANCE_KINDS)}"
        )
    if payload.result not in FIRE_MAINTENANCE_RESULTS:
        raise _unprocessable(
            f"Неизвестный результат {payload.result!r}; допустимые: "
            f"{', '.join(FIRE_MAINTENANCE_RESULTS)}"
        )
    if payload.performed_on > date.today():
        raise _unprocessable(
            "Дата работы не может быть в будущем — запись о работе это "
            "свидетельство, а не план"
        )

    record = FireMaintenanceRecord(
        tenant_id=str(tenant.id),
        equipment_id=unit.id,
        kind=payload.kind,
        performed_on=payload.performed_on,
        performer=(payload.performer or None),
        result=payload.result,
        notes=(payload.notes or None),
        next_due=payload.next_due,
    )
    session.add(record)

    # Проваленная работа срок НЕ двигает: перенос означал бы «исправно до
    # следующего раза» — просрочка ушла бы с экрана, а неисправность осталась.
    shifted = (
        payload.next_due is not None
        and payload.result in FIRE_MAINTENANCE_PASSING_RESULTS
    )
    if shifted:
        setattr(unit, FIRE_MAINTENANCE_DUE_FIELD[payload.kind], payload.next_due)

    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="FireMaintenanceRecord",
        object_id=record.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": record.id}}},
        details={
            "entity": "FireMaintenanceRecord",
            "kind": record.kind,
            "equipment_id": unit.id,
            "shifted_due": shifted,
        },
    )
    await session.commit()
    await session.refresh(record)
    return _maintenance_read(record, shifted=shifted)


def _drill_status(drill: FireDrill, today: date) -> str:
    """planned / held / overdue — считается ПРИ ЧТЕНИИ.

    Хранимый статус разъехался бы с календарём в первую же ночь: срок
    наступает сам, без запроса на изменение (тот же довод, что у просрочек
    средств в /readiness).
    """

    if drill.held_on is not None:
        return "held"
    return "overdue" if drill.planned_on < today else "planned"


def _drill_read(drill: FireDrill, today: date) -> FireDrillRead:
    return FireDrillRead(
        id=drill.id,
        kind=drill.kind,
        kind_label=FIRE_DRILL_KINDS.get(drill.kind, drill.kind),
        title=drill.title,
        planned_on=drill.planned_on,
        held_on=drill.held_on,
        site_id=drill.site_id,
        scenario=drill.scenario,
        participants=drill.participants,
        outcome=drill.outcome,
        outcome_label=(
            FIRE_DRILL_OUTCOMES.get(drill.outcome, drill.outcome)
            if drill.outcome
            else None
        ),
        findings=drill.findings,
        status=_drill_status(drill, today),
    )


def _validate_drill(
    *, kind: str | None, outcome: str | None, held_on: date | None, has_outcome_field: bool
) -> None:
    """Протокол обязан быть протоколом: проведена → есть результат, и наоборот.

    Без этой пары требование ТЗ «протоколы, анализ» выполнялось бы на бумаге:
    запись «провели» без оценки нечего анализировать, а оценка без даты
    проведения — выдумка о событии, которого не было.
    """

    if kind is not None and kind not in FIRE_DRILL_KINDS:
        raise _unprocessable(
            f"Неизвестный вид тренировки {kind!r}; допустимые: "
            f"{', '.join(FIRE_DRILL_KINDS)}"
        )
    if outcome is not None and outcome not in FIRE_DRILL_OUTCOMES:
        raise _unprocessable(
            f"Неизвестный результат {outcome!r}; допустимые: "
            f"{', '.join(FIRE_DRILL_OUTCOMES)}"
        )
    if held_on is not None and held_on > date.today():
        raise _unprocessable(
            "Дата проведения не может быть в будущем — это план, а не протокол"
        )
    if held_on is not None and outcome is None:
        raise _unprocessable(
            "У проведённой тренировки обязателен результат: "
            f"{', '.join(FIRE_DRILL_OUTCOMES)}"
        )
    if outcome is not None and held_on is None and has_outcome_field:
        raise _unprocessable(
            "Результат нельзя выставить, пока тренировка не проведена — "
            "укажите дату проведения"
        )


async def _get_drill_or_404(
    session: AsyncSession, tenant: Tenant, drill_id: str
) -> FireDrill:
    stmt = select(FireDrill).where(
        FireDrill.id == drill_id,
        FireDrill.tenant_id == tenant.id,
        FireDrill.deleted_at.is_(None),
    )
    drill = (await session.execute(stmt)).scalar_one_or_none()
    if drill is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="FIRE_DRILL_NOT_FOUND",
                message="Fire drill not found",
                error_type="fire_safety",
            ),
        )
    return drill


@router.get("/drills", response_model=FireDrillPage)
async def list_drills(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    status_filter: str | None = Query(default=None, alias="status"),
    site_id: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> FireDrillPage:
    """План-график тренировок: и назначенные, и проведённые, в одном реестре."""

    TenantContextValidator.ensure_tenant_context(tenant)
    today = date.today()
    stmt = select(FireDrill).where(
        FireDrill.tenant_id == tenant.id,
        FireDrill.deleted_at.is_(None),
    )
    if site_id:
        stmt = stmt.where(FireDrill.site_id == site_id)
    # Статус вычисляемый, поэтому фильтр по нему выражается условиями на даты,
    # а не сравнением с колонкой (колонки нет — и не должно быть).
    if status_filter == "held":
        stmt = stmt.where(FireDrill.held_on.is_not(None))
    elif status_filter == "overdue":
        stmt = stmt.where(FireDrill.held_on.is_(None), FireDrill.planned_on < today)
    elif status_filter == "planned":
        stmt = stmt.where(FireDrill.held_on.is_(None), FireDrill.planned_on >= today)
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        (
            await session.execute(
                stmt.order_by(FireDrill.planned_on.desc()).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return FireDrillPage(items=[_drill_read(r, today) for r in rows], total=total)


@router.post("/drills", response_model=FireDrillRead, status_code=status.HTTP_201_CREATED)
async def create_drill(
    request: Request,
    payload: FireDrillCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> FireDrillRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _validate_payload(session, tenant, kind=None, site_id=payload.site_id)
    _validate_drill(
        kind=payload.kind,
        outcome=payload.outcome,
        held_on=payload.held_on,
        has_outcome_field=True,
    )
    drill = FireDrill(
        tenant_id=str(tenant.id),
        kind=payload.kind,
        title=payload.title.strip(),
        planned_on=payload.planned_on,
        held_on=payload.held_on,
        site_id=payload.site_id,
        scenario=(payload.scenario or None),
        participants=payload.participants,
        outcome=payload.outcome,
        findings=(payload.findings or None),
    )
    session.add(drill)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="FireDrill",
        object_id=drill.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": drill.id}}},
        details={"entity": "FireDrill", "kind": drill.kind},
    )
    await session.commit()
    await session.refresh(drill)
    return _drill_read(drill, date.today())


@router.patch("/drills/{drill_id}", response_model=FireDrillRead)
async def update_drill(
    request: Request,
    drill_id: str,
    payload: FireDrillUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> FireDrillRead:
    """Протокол дописывается сюда же: провели → дата, участники, результат."""

    TenantContextValidator.ensure_tenant_context(tenant)
    drill = await _get_drill_or_404(session, tenant, drill_id)
    data = payload.model_dump(exclude_unset=True)
    await _validate_payload(session, tenant, kind=None, site_id=data.get("site_id"))
    # Проверяем ИТОГОВОЕ состояние записи, а не только присланные поля: иначе
    # «провели» одним запросом и «результат» другим прошли бы оба, оставив
    # запись в запрещённом состоянии.
    _validate_drill(
        kind=data.get("kind"),
        outcome=data["outcome"] if "outcome" in data else drill.outcome,
        held_on=data["held_on"] if "held_on" in data else drill.held_on,
        has_outcome_field="outcome" in data,
    )
    before = _drill_read(drill, date.today()).model_dump()
    for field in (
        "kind",
        "title",
        "planned_on",
        "held_on",
        "site_id",
        "scenario",
        "participants",
        "outcome",
        "findings",
    ):
        if field in data:
            value = data[field]
            if field == "title" and (value is None or not str(value).strip()):
                raise _unprocessable("title cannot be empty")
            if field == "planned_on" and value is None:
                raise _unprocessable("planned_on cannot be empty")
            setattr(drill, field, value.strip() if isinstance(value, str) else value)
    after = _drill_read(drill, date.today()).model_dump()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="FireDrill",
        object_id=drill.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "FireDrill"},
    )
    await session.commit()
    await session.refresh(drill)
    return _drill_read(drill, date.today())


@router.get("/readiness", response_model=FireReadinessRead)
async def fire_readiness(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> FireReadinessRead:
    """Готовность к проверке МЧС: сколько сроков уже горит и сколько сгорит скоро.

    Просрочка считается ПРИ ЧТЕНИИ, а не фоновой задачей: задача ходит по
    расписанию (или падает), и всё это время сводка показывала бы вчерашнюю
    правду (тот же довод, что у гейта временного доступа BIZ-61 срез-3).
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    today = date.today()
    soon = today + timedelta(days=_DUE_SOON_DAYS)

    base = select(FireSafetyEquipment).where(
        FireSafetyEquipment.tenant_id == tenant.id,
        FireSafetyEquipment.deleted_at.is_(None),
        FireSafetyEquipment.status == "active",
    )
    rows = (await session.execute(base)).scalars().all()
    overdue_recharge = sum(
        1 for r in rows if r.recharge_due is not None and r.recharge_due < today
    )
    overdue_inspection = sum(
        1 for r in rows if r.inspection_due is not None and r.inspection_due < today
    )
    due_soon = sum(
        1
        for r in rows
        if (r.recharge_due is not None and today <= r.recharge_due <= soon)
        or (r.inspection_due is not None and today <= r.inspection_due <= soon)
    )
    # Разд. 54.1 «контроль сроков»: просроченный противопожарный инструктаж —
    # такое же нарушение к приходу МЧС, как непроверенный огнетушитель.
    fire_types = [
        code
        for code, discipline in BRIEFING_TYPE_DISCIPLINE.items()
        if discipline is Discipline.FIRE_SAFETY
    ]
    overdue_briefings = int(
        await session.scalar(
            select(func.count())
            .select_from(BriefingEntry)
            .where(
                BriefingEntry.tenant_id == tenant.id,
                BriefingEntry.briefing_type.in_(fire_types),
                BriefingEntry.valid_until.is_not(None),
                BriefingEntry.valid_until < func.now(),
            )
        )
        or 0
    )

    # Разд. 54.1 «Документы ПБ»: просроченный пересмотр инструкции или приказа —
    # такое же нарушение к приходу инспектора, как непроверенный огнетушитель.
    # ГРАНИЦА: сколько документов ОБЯЗАТЕЛЬНО, платформа не судит — декларация
    # нужна не всем объектам, план эвакуации — не всем этажам, а признаков
    # применимости в данных нет (тот же довод, что у интервала тренировок).
    fire_documents = int(
        await session.scalar(
            select(func.count())
            .select_from(FireSafetyDocument)
            .where(
                FireSafetyDocument.tenant_id == tenant.id,
                FireSafetyDocument.deleted_at.is_(None),
            )
        )
        or 0
    )
    overdue_documents = int(
        await session.scalar(
            select(func.count())
            .select_from(FireSafetyDocument)
            .where(
                FireSafetyDocument.tenant_id == tenant.id,
                FireSafetyDocument.deleted_at.is_(None),
                FireSafetyDocument.review_due.is_not(None),
                FireSafetyDocument.review_due < today,
            )
        )
        or 0
    )

    # Разд. 54.1 «регламентные работы»: срок без единой записи о работе — это
    # обещание, а не доказательство. Инспектор спрашивает не «когда следующая
    # поверка», а «покажите, что предыдущая была», поэтому число средств без
    # подтверждения стоит в сводке рядом с просрочками.
    confirmed_ids = set(
        (
            await session.execute(
                select(FireMaintenanceRecord.equipment_id.distinct()).where(
                    FireMaintenanceRecord.tenant_id == tenant.id,
                    FireMaintenanceRecord.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    units_without_maintenance = sum(1 for r in rows if r.id not in confirmed_ids)

    # Разд. 54.1 «Тренировки и учения»: просроченный план тренировки — такое же
    # нарушение к приходу инспектора, как непроверенный огнетушитель.
    # ГРАНИЦА: интервал «не реже раза в полгода» (ППР РФ) здесь НЕ судится —
    # норма обязательна для объектов с массовым пребыванием людей, а признака
    # массового пребывания у площадки в данных нет. Отдаём факт (дата последней
    # и сколько дней прошло), вывод делает специалист; иначе платформа красила
    # бы в нарушение по угаданной применимости нормы.
    overdue_drills = int(
        await session.scalar(
            select(func.count())
            .select_from(FireDrill)
            .where(
                FireDrill.tenant_id == tenant.id,
                FireDrill.deleted_at.is_(None),
                FireDrill.held_on.is_(None),
                FireDrill.planned_on < today,
            )
        )
        or 0
    )
    planned_drills = int(
        await session.scalar(
            select(func.count())
            .select_from(FireDrill)
            .where(
                FireDrill.tenant_id == tenant.id,
                FireDrill.deleted_at.is_(None),
                FireDrill.held_on.is_(None),
                FireDrill.planned_on >= today,
            )
        )
        or 0
    )
    last_drill_on = await session.scalar(
        select(func.max(FireDrill.held_on)).where(
            FireDrill.tenant_id == tenant.id,
            FireDrill.deleted_at.is_(None),
            FireDrill.held_on.is_not(None),
        )
    )
    return FireReadinessRead(
        fire_documents=fire_documents,
        overdue_documents=overdue_documents,
        units_without_maintenance=units_without_maintenance,
        overdue_drills=overdue_drills,
        planned_drills=planned_drills,
        last_drill_on=last_drill_on,
        days_since_last_drill=(
            (today - last_drill_on).days if last_drill_on is not None else None
        ),
        total_units=len(rows),
        overdue_recharge=overdue_recharge,
        overdue_inspection=overdue_inspection,
        due_soon=due_soon,
        due_soon_days=_DUE_SOON_DAYS,
        overdue_fire_briefings=overdue_briefings,
        # Доп. №1 разд. 57.4: открытые происшествия контура — той же формулой,
        # что разрез «по дисциплинам» у директора (срез-49).
        incidents_open=await open_incidents_count(session, str(tenant.id), Discipline.FIRE_SAFETY),
    )
