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
    FIRE_DRILL_KINDS,
    FIRE_DRILL_OUTCOMES,
    FIRE_EQUIPMENT_KINDS,
    FireDrill,
    FireSafetyEquipment,
)
from app.models.master_data import Site
from app.models.models import Tenant
from app.schemas.fire_safety import (
    FireDrillCreate,
    FireDrillPage,
    FireDrillRead,
    FireDrillUpdate,
    FireEquipmentCreate,
    FireEquipmentPage,
    FireEquipmentRead,
    FireEquipmentUpdate,
    FireReadinessRead,
)
from app.services.audit import AuditService, field_level_diff

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
    return FireEquipmentPage(
        items=[FireEquipmentRead.model_validate(r) for r in rows], total=total
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
    )
