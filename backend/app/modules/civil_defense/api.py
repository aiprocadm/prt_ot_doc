"""Контур ГО и ЧС, собственные ручки (Доп. №1 разд. 56.1, срез-1).

Реестр нештатных формирований (НАСФ/НФГО) с составами из людей ядра. До этого
среза по разд. 56 не было ни одной сущности — дисциплина существовала
словарной строкой, а весь контент сводился к комплекту документов GOCHS_BASE.

Гейт модуля — роутерный (разд. 61.3): на каждом роуте по построению,
аутентификация РАНЬШЕ гейта (иначе без токена вернулся бы 404 вместо 401),
отключённый (но выдававшийся) модуль читается (read-only, BIZ-61 срез-6).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.errors import api_problem_detail
from app.core.feature_flags import is_module_enabled, raise_for_disabled_module
from app.core.security import AccessContext, abac, rbac
from app.core.tenant_validation import TenantContextValidator
from app.models.civil_defense import (
    CD_DRILL_KINDS,
    CD_DRILL_OUTCOMES,
    CD_DRILL_STATUS_TITLES,
    CD_FORMATION_KINDS,
    CD_MEMBER_STATUS_TITLES,
    CivilDefenseDrill,
    CivilDefenseFormation,
    CivilDefenseFormationMember,
)
from app.models.master_data import Person
from app.models.models import Tenant
from app.schemas.civil_defense import (
    CivilDefenseReadinessRead,
    DrillCreate,
    DrillPage,
    DrillRead,
    DrillUpdate,
    FormationCreate,
    FormationMemberCreate,
    FormationMemberPage,
    FormationMemberRead,
    FormationMemberUpdate,
    FormationPage,
    FormationRead,
    FormationUpdate,
)
from app.services.audit import AuditService, field_level_diff

router = APIRouter(prefix="/civil-defense", tags=["civil-defense"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_ROLES = ["admin", "owner", "ot_pb_lead", "ot_specialist"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


Access = Annotated[
    AccessContext,
    Depends(
        abac(_tenant_resource_id, required_roles=_ROLES, action="manage civil defense")
    ),
]

_FEATURE_CODE = "civil_defense"


async def _require_civil_defense(
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
            error_type="civil_defense",
            disabled_code="CIVIL_DEFENSE_DISABLED",
            disabled_message="Civil defense module is not enabled for this tenant",
        )


router.dependencies.append(Depends(_require_civil_defense))


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(
            code="CIVIL_DEFENSE_VALIDATION_ERROR",
            message=message,
            error_type="civil_defense",
        ),
    )


def _full_name(person: Person) -> str:
    parts = [person.last_name, person.first_name, person.middle_name]
    return " ".join(part for part in parts if part)


async def _get_person_or_404(
    session: AsyncSession, tenant: Tenant, person_id: str
) -> Person:
    stmt = select(Person).where(
        Person.id == person_id,
        Person.tenant_id == tenant.id,
        Person.deleted_at.is_(None),
    )
    person = (await session.execute(stmt)).scalar_one_or_none()
    if person is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="PERSON_NOT_FOUND",
                message="Person not found",
                error_type="civil_defense",
            ),
        )
    return person


async def _get_formation_or_404(
    session: AsyncSession, tenant: Tenant, formation_id: str
) -> CivilDefenseFormation:
    stmt = select(CivilDefenseFormation).where(
        CivilDefenseFormation.id == formation_id,
        CivilDefenseFormation.tenant_id == tenant.id,
        CivilDefenseFormation.deleted_at.is_(None),
    )
    formation = (await session.execute(stmt)).scalar_one_or_none()
    if formation is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="CD_FORMATION_NOT_FOUND",
                message="Formation not found",
                error_type="civil_defense",
            ),
        )
    return formation


async def _ensure_name_free(
    session: AsyncSession, tenant: Tenant, name: str, *, exclude_id: str | None = None
) -> None:
    """Название уникально в организации: два одинаковых — ошибка ввода."""

    stmt = select(CivilDefenseFormation.id).where(
        CivilDefenseFormation.tenant_id == tenant.id,
        CivilDefenseFormation.name == name,
        CivilDefenseFormation.deleted_at.is_(None),
    )
    if exclude_id:
        stmt = stmt.where(CivilDefenseFormation.id != exclude_id)
    if (await session.execute(stmt)).scalar_one_or_none() is not None:
        raise _unprocessable(f"Формирование {name!r} уже заведено")


def _validate_kind(kind: str) -> None:
    if kind not in CD_FORMATION_KINDS:
        raise _unprocessable(
            f"Неизвестный вид формирования {kind!r}; допустимые: "
            f"{', '.join(CD_FORMATION_KINDS)}"
        )


async def _active_members_map(
    session: AsyncSession, tenant: Tenant, formation_ids: list[str]
) -> dict[str, int]:
    """Действующая численность по формированиям — одним запросом, а не N+1."""

    if not formation_ids:
        return {}
    rows = await session.execute(
        select(CivilDefenseFormationMember.formation_id, func.count())
        .where(
            CivilDefenseFormationMember.tenant_id == tenant.id,
            CivilDefenseFormationMember.deleted_at.is_(None),
            CivilDefenseFormationMember.released_on.is_(None),
            CivilDefenseFormationMember.formation_id.in_(formation_ids),
        )
        .group_by(CivilDefenseFormationMember.formation_id)
    )
    return {row[0]: int(row[1]) for row in rows}


async def _commander_names(
    session: AsyncSession, tenant: Tenant, person_ids: list[str]
) -> dict[str, str]:
    if not person_ids:
        return {}
    rows = (
        (
            await session.execute(
                select(Person).where(
                    Person.tenant_id == tenant.id, Person.id.in_(person_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    return {str(p.id): _full_name(p) for p in rows}


def _formation_read(
    formation: CivilDefenseFormation,
    *,
    commander_name: str | None,
    members_active: int,
) -> FormationRead:
    return FormationRead(
        id=formation.id,
        name=formation.name,
        kind=formation.kind,
        kind_label=CD_FORMATION_KINDS.get(formation.kind, formation.kind),
        purpose=formation.purpose,
        commander_person_id=formation.commander_person_id,
        commander_name=commander_name,
        equipment_notes=formation.equipment_notes,
        notes=formation.notes,
        members_active=members_active,
    )


def _member_read(
    member: CivilDefenseFormationMember, person_name: str
) -> FormationMemberRead:
    status_value = "released" if member.released_on is not None else "active"
    return FormationMemberRead(
        id=member.id,
        formation_id=member.formation_id,
        person_id=member.person_id,
        person_name=person_name,
        role_in_formation=member.role_in_formation,
        assigned_on=member.assigned_on,
        released_on=member.released_on,
        notes=member.notes,
        status=status_value,
        status_label=CD_MEMBER_STATUS_TITLES.get(status_value, status_value),
    )


@router.get("/formations", response_model=FormationPage)
async def list_formations(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    kind: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> FormationPage:
    """Реестр нештатных формирований (НАСФ/НФГО)."""

    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(CivilDefenseFormation).where(
        CivilDefenseFormation.tenant_id == tenant.id,
        CivilDefenseFormation.deleted_at.is_(None),
    )
    if kind:
        stmt = stmt.where(CivilDefenseFormation.kind == kind)
    total = int(
        await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )
    rows = (
        (
            await session.execute(
                stmt.order_by(CivilDefenseFormation.name).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    counts = await _active_members_map(session, tenant, [r.id for r in rows])
    commanders = await _commander_names(
        session, tenant, [r.commander_person_id for r in rows if r.commander_person_id]
    )
    return FormationPage(
        items=[
            _formation_read(
                r,
                commander_name=commanders.get(r.commander_person_id or ""),
                members_active=counts.get(r.id, 0),
            )
            for r in rows
        ],
        total=total,
    )


@router.post(
    "/formations", response_model=FormationRead, status_code=status.HTTP_201_CREATED
)
async def create_formation(
    request: Request,
    payload: FormationCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> FormationRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _validate_kind(payload.kind)
    name = payload.name.strip()
    await _ensure_name_free(session, tenant, name)
    commander_name: str | None = None
    if payload.commander_person_id:
        commander = await _get_person_or_404(
            session, tenant, payload.commander_person_id
        )
        commander_name = _full_name(commander)

    formation = CivilDefenseFormation(
        tenant_id=str(tenant.id),
        name=name,
        kind=payload.kind,
        purpose=(payload.purpose or None),
        commander_person_id=payload.commander_person_id or None,
        equipment_notes=(payload.equipment_notes or None),
        notes=(payload.notes or None),
    )
    session.add(formation)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="CivilDefenseFormation",
        object_id=formation.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": formation.id}}},
        details={"entity": "CivilDefenseFormation", "name": formation.name},
    )
    await session.commit()
    await session.refresh(formation)
    return _formation_read(formation, commander_name=commander_name, members_active=0)


@router.patch("/formations/{formation_id}", response_model=FormationRead)
async def update_formation(
    request: Request,
    formation_id: str,
    payload: FormationUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> FormationRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    formation = await _get_formation_or_404(session, tenant, formation_id)
    before = {
        "name": formation.name,
        "kind": formation.kind,
        "purpose": formation.purpose,
        "commander_person_id": formation.commander_person_id,
        "equipment_notes": formation.equipment_notes,
        "notes": formation.notes,
    }
    data = payload.model_dump(exclude_unset=True)
    if data.get("kind"):
        _validate_kind(str(data["kind"]))
        formation.kind = str(data["kind"])
    if data.get("name"):
        name = str(data["name"]).strip()
        await _ensure_name_free(session, tenant, name, exclude_id=formation.id)
        formation.name = name
    if "commander_person_id" in data:
        if data["commander_person_id"]:
            await _get_person_or_404(session, tenant, str(data["commander_person_id"]))
        formation.commander_person_id = data["commander_person_id"] or None
    for field in ("purpose", "equipment_notes", "notes"):
        if field in data:
            setattr(formation, field, data[field] or None)
    await session.flush()
    after = {
        "name": formation.name,
        "kind": formation.kind,
        "purpose": formation.purpose,
        "commander_person_id": formation.commander_person_id,
        "equipment_notes": formation.equipment_notes,
        "notes": formation.notes,
    }
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="CivilDefenseFormation",
        object_id=formation.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "CivilDefenseFormation"},
    )
    await session.commit()
    await session.refresh(formation)
    counts = await _active_members_map(session, tenant, [formation.id])
    commanders = await _commander_names(
        session,
        tenant,
        [formation.commander_person_id] if formation.commander_person_id else [],
    )
    return _formation_read(
        formation,
        commander_name=commanders.get(formation.commander_person_id or ""),
        members_active=counts.get(formation.id, 0),
    )


@router.get("/formations/{formation_id}/members", response_model=FormationMemberPage)
async def list_members(
    formation_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> FormationMemberPage:
    """Состав формирования, включая выведенных (история цела)."""

    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_formation_or_404(session, tenant, formation_id)
    stmt = select(CivilDefenseFormationMember).where(
        CivilDefenseFormationMember.tenant_id == tenant.id,
        CivilDefenseFormationMember.formation_id == formation_id,
        CivilDefenseFormationMember.deleted_at.is_(None),
    )
    total = int(
        await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )
    rows = (
        (
            await session.execute(
                stmt.order_by(CivilDefenseFormationMember.created_at)
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    names = await _commander_names(session, tenant, [r.person_id for r in rows])
    return FormationMemberPage(
        items=[_member_read(r, names.get(r.person_id, "—")) for r in rows],
        total=total,
    )


@router.post(
    "/formations/{formation_id}/members",
    response_model=FormationMemberRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    request: Request,
    formation_id: str,
    payload: FormationMemberCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> FormationMemberRead:
    """Включить человека из ядра в состав.

    Повторное включение выведенного — ВОЗВРАЩЕНИЕ: та же строка, дата вывода
    снимается (200, не 201). Дубль действующего — ошибка ввода (422).
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_formation_or_404(session, tenant, formation_id)
    person = await _get_person_or_404(session, tenant, payload.person_id)

    existing = (
        await session.execute(
            select(CivilDefenseFormationMember).where(
                CivilDefenseFormationMember.tenant_id == tenant.id,
                CivilDefenseFormationMember.formation_id == formation_id,
                CivilDefenseFormationMember.person_id == payload.person_id,
                CivilDefenseFormationMember.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.released_on is None:
            raise _unprocessable(
                f"{_full_name(person)} уже в составе этого формирования"
            )
        existing.released_on = None
        if payload.assigned_on is not None:
            existing.assigned_on = payload.assigned_on
        await session.flush()
        await AuditService(session).log_event(
            tenant_id=str(tenant.id),
            action="update",
            object_type="CivilDefenseFormationMember",
            object_id=existing.id,
            user_id=access.user.id,
            ip=request.client.host if request.client else "unknown",
            request_id=getattr(request.state, "trace_id", None),
            user_agent=request.headers.get("user-agent"),
            changed_fields={
                "fields": {"released_on": {"before": "set", "after": None}}
            },
            details={"entity": "CivilDefenseFormationMember", "rejoined": True},
        )
        await session.commit()
        await session.refresh(existing)
        # 200, а не 201: строка не создана, человек ВЕРНУЛСЯ в состав.
        body = _member_read(existing, _full_name(person)).model_dump(mode="json")
        return JSONResponse(status_code=status.HTTP_200_OK, content=body)  # type: ignore[return-value]

    member = CivilDefenseFormationMember(
        tenant_id=str(tenant.id),
        formation_id=formation_id,
        person_id=payload.person_id,
        role_in_formation=(payload.role_in_formation or None),
        assigned_on=payload.assigned_on,
        notes=(payload.notes or None),
    )
    session.add(member)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="CivilDefenseFormationMember",
        object_id=member.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": member.id}}},
        details={"entity": "CivilDefenseFormationMember"},
    )
    await session.commit()
    await session.refresh(member)
    return _member_read(member, _full_name(person))


@router.patch(
    "/formations/{formation_id}/members/{member_id}",
    response_model=FormationMemberRead,
)
async def update_member(
    request: Request,
    formation_id: str,
    member_id: str,
    payload: FormationMemberUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> FormationMemberRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_formation_or_404(session, tenant, formation_id)
    stmt = select(CivilDefenseFormationMember).where(
        CivilDefenseFormationMember.id == member_id,
        CivilDefenseFormationMember.tenant_id == tenant.id,
        CivilDefenseFormationMember.formation_id == formation_id,
        CivilDefenseFormationMember.deleted_at.is_(None),
    )
    member = (await session.execute(stmt)).scalar_one_or_none()
    if member is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="CD_MEMBER_NOT_FOUND",
                message="Formation member not found",
                error_type="civil_defense",
            ),
        )
    before = {
        "role_in_formation": member.role_in_formation,
        "assigned_on": str(member.assigned_on),
        "released_on": str(member.released_on),
        "notes": member.notes,
    }
    data = payload.model_dump(exclude_unset=True)
    if "released_on" in data:
        member.released_on = data["released_on"]
    if "assigned_on" in data:
        member.assigned_on = data["assigned_on"]
    for field in ("role_in_formation", "notes"):
        if field in data:
            setattr(member, field, data[field] or None)
    await session.flush()
    after = {
        "role_in_formation": member.role_in_formation,
        "assigned_on": str(member.assigned_on),
        "released_on": str(member.released_on),
        "notes": member.notes,
    }
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="CivilDefenseFormationMember",
        object_id=member.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "CivilDefenseFormationMember"},
    )
    await session.commit()
    await session.refresh(member)
    person = await _get_person_or_404(session, tenant, member.person_id)
    return _member_read(member, _full_name(person))


# --- Учения и тренировки ГО: план-график, протокол, журнал (разд. 56.1) -----


def _drill_status(drill: CivilDefenseDrill, today: date) -> str:
    """planned / held / overdue — считается ПРИ ЧТЕНИИ.

    Хранимый статус разъехался бы с календарём в первую же ночь: срок
    наступает сам, без запроса на изменение (прецедент тренировок ПБ).
    """

    if drill.held_on is not None:
        return "held"
    return "overdue" if drill.planned_on < today else "planned"


def _drill_read(
    drill: CivilDefenseDrill, today: date, formation_name: str | None
) -> DrillRead:
    status_value = _drill_status(drill, today)
    return DrillRead(
        id=drill.id,
        kind=drill.kind,
        kind_label=CD_DRILL_KINDS.get(drill.kind, drill.kind),
        title=drill.title,
        planned_on=drill.planned_on,
        held_on=drill.held_on,
        formation_id=drill.formation_id,
        formation_name=formation_name,
        site_id=drill.site_id,
        scenario=drill.scenario,
        participants=drill.participants,
        outcome=drill.outcome,
        outcome_label=(
            CD_DRILL_OUTCOMES.get(drill.outcome, drill.outcome)
            if drill.outcome
            else None
        ),
        findings=drill.findings,
        status=status_value,
        status_label=CD_DRILL_STATUS_TITLES.get(status_value, status_value),
    )


def _validate_drill(
    *,
    kind: str | None,
    outcome: str | None,
    held_on: date | None,
    has_outcome_field: bool,
) -> None:
    """Протокол обязан быть протоколом: проведено → есть результат, и наоборот.

    Правила намеренно те же, что у тренировок ПБ: без этой пары требование ТЗ
    «журналы» выполнялось бы на бумаге — запись «провели» без оценки нечего
    анализировать, а оценка без даты проведения это выдумка о событии,
    которого не было.
    """

    if kind is not None and kind not in CD_DRILL_KINDS:
        raise _unprocessable(
            f"Неизвестный вид учения {kind!r}; допустимые: "
            f"{', '.join(CD_DRILL_KINDS)}"
        )
    if outcome is not None and outcome not in CD_DRILL_OUTCOMES:
        raise _unprocessable(
            f"Неизвестный результат {outcome!r}; допустимые: "
            f"{', '.join(CD_DRILL_OUTCOMES)}"
        )
    if held_on is not None and held_on > date.today():
        raise _unprocessable(
            "Дата проведения не может быть в будущем — это план, а не протокол"
        )
    if held_on is not None and outcome is None:
        raise _unprocessable(
            "У проведённого учения обязателен результат: "
            f"{', '.join(CD_DRILL_OUTCOMES)}"
        )
    if outcome is not None and held_on is None and has_outcome_field:
        raise _unprocessable(
            "Результат нельзя выставить, пока учение не проведено — "
            "укажите дату проведения"
        )


async def _get_drill_or_404(
    session: AsyncSession, tenant: Tenant, drill_id: str
) -> CivilDefenseDrill:
    stmt = select(CivilDefenseDrill).where(
        CivilDefenseDrill.id == drill_id,
        CivilDefenseDrill.tenant_id == tenant.id,
        CivilDefenseDrill.deleted_at.is_(None),
    )
    drill = (await session.execute(stmt)).scalar_one_or_none()
    if drill is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="CD_DRILL_NOT_FOUND",
                message="Drill not found",
                error_type="civil_defense",
            ),
        )
    return drill


async def _formation_names(
    session: AsyncSession, tenant: Tenant, formation_ids: list[str]
) -> dict[str, str]:
    """Названия формирований одним запросом, а не N+1."""

    ids = [fid for fid in formation_ids if fid]
    if not ids:
        return {}
    rows = (
        (
            await session.execute(
                select(CivilDefenseFormation).where(
                    CivilDefenseFormation.tenant_id == tenant.id,
                    CivilDefenseFormation.id.in_(ids),
                )
            )
        )
        .scalars()
        .all()
    )
    return {str(row.id): row.name for row in rows}


@router.get("/drills", response_model=DrillPage)
async def list_drills(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    status_filter: str | None = Query(default=None, alias="status"),
    formation_id: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> DrillPage:
    """План-график учений: и назначенные, и проведённые, в одном реестре.

    ``status=held`` — это и есть «журнал» из требования: реестр с фактическими
    датами проведения.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    today = date.today()
    stmt = select(CivilDefenseDrill).where(
        CivilDefenseDrill.tenant_id == tenant.id,
        CivilDefenseDrill.deleted_at.is_(None),
    )
    if formation_id:
        stmt = stmt.where(CivilDefenseDrill.formation_id == formation_id)
    if status_filter == "held":
        stmt = stmt.where(CivilDefenseDrill.held_on.is_not(None))
    elif status_filter == "planned":
        stmt = stmt.where(
            CivilDefenseDrill.held_on.is_(None),
            CivilDefenseDrill.planned_on >= today,
        )
    elif status_filter == "overdue":
        stmt = stmt.where(
            CivilDefenseDrill.held_on.is_(None),
            CivilDefenseDrill.planned_on < today,
        )
    total = int(
        await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )
    rows = (
        (
            await session.execute(
                stmt.order_by(CivilDefenseDrill.planned_on.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    names = await _formation_names(
        session, tenant, [r.formation_id for r in rows if r.formation_id]
    )
    return DrillPage(
        items=[
            _drill_read(r, today, names.get(r.formation_id or "")) for r in rows
        ],
        total=total,
    )


@router.post("/drills", response_model=DrillRead, status_code=status.HTTP_201_CREATED)
async def create_drill(
    request: Request,
    payload: DrillCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> DrillRead:
    """Завести учение в план-график. Рождается ЗАПЛАНИРОВАННЫМ."""

    TenantContextValidator.ensure_tenant_context(tenant)
    _validate_drill(
        kind=payload.kind, outcome=None, held_on=None, has_outcome_field=False
    )
    formation_name: str | None = None
    if payload.formation_id:
        formation = await _get_formation_or_404(
            session, tenant, payload.formation_id
        )
        formation_name = formation.name

    drill = CivilDefenseDrill(
        tenant_id=str(tenant.id),
        kind=payload.kind,
        title=payload.title.strip(),
        planned_on=payload.planned_on,
        formation_id=payload.formation_id or None,
        site_id=payload.site_id or None,
        scenario=(payload.scenario or None),
        participants=payload.participants,
    )
    session.add(drill)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="CivilDefenseDrill",
        object_id=drill.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": drill.id}}},
        details={"entity": "CivilDefenseDrill", "title": drill.title},
    )
    await session.commit()
    await session.refresh(drill)
    return _drill_read(drill, date.today(), formation_name)


@router.patch("/drills/{drill_id}", response_model=DrillRead)
async def update_drill(
    request: Request,
    drill_id: str,
    payload: DrillUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> DrillRead:
    """Внести протокол проведения или поправить план-график."""

    TenantContextValidator.ensure_tenant_context(tenant)
    drill = await _get_drill_or_404(session, tenant, drill_id)
    data = payload.model_dump(exclude_unset=True)
    _validate_drill(
        kind=data.get("kind"),
        outcome=data.get("outcome", drill.outcome),
        held_on=data.get("held_on", drill.held_on),
        has_outcome_field=True,
    )
    before = {
        "kind": drill.kind,
        "title": drill.title,
        "planned_on": str(drill.planned_on),
        "held_on": str(drill.held_on),
        "formation_id": drill.formation_id,
        "outcome": drill.outcome,
        "participants": drill.participants,
        "findings": drill.findings,
    }
    if data.get("kind"):
        drill.kind = str(data["kind"])
    if data.get("title"):
        drill.title = str(data["title"]).strip()
    if data.get("planned_on") is not None:
        drill.planned_on = data["planned_on"]
    if "held_on" in data:
        drill.held_on = data["held_on"]
    if "outcome" in data:
        drill.outcome = data["outcome"] or None
    if "formation_id" in data:
        if data["formation_id"]:
            await _get_formation_or_404(session, tenant, str(data["formation_id"]))
        drill.formation_id = data["formation_id"] or None
    if "site_id" in data:
        drill.site_id = data["site_id"] or None
    if "participants" in data:
        drill.participants = data["participants"]
    for field in ("scenario", "findings"):
        if field in data:
            setattr(drill, field, data[field] or None)
    await session.flush()
    after = {
        "kind": drill.kind,
        "title": drill.title,
        "planned_on": str(drill.planned_on),
        "held_on": str(drill.held_on),
        "formation_id": drill.formation_id,
        "outcome": drill.outcome,
        "participants": drill.participants,
        "findings": drill.findings,
    }
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="CivilDefenseDrill",
        object_id=drill.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "CivilDefenseDrill"},
    )
    await session.commit()
    await session.refresh(drill)
    names = await _formation_names(
        session, tenant, [drill.formation_id] if drill.formation_id else []
    )
    return _drill_read(drill, date.today(), names.get(drill.formation_id or ""))


@router.get("/readiness", response_model=CivilDefenseReadinessRead)
async def civil_defense_readiness(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> CivilDefenseReadinessRead:
    """Сводка: формирования по видам, командиры, действующая численность.

    ГРАНИЦА: платформа НЕ решает, сколько формирований нужно и каков их штат —
    это категория организации по ГО и решения органа управления ГОЧС. «Без
    командира» — факт о внесённом, а не вердикт о нарушении.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    formations = (
        (
            await session.execute(
                select(CivilDefenseFormation).where(
                    CivilDefenseFormation.tenant_id == tenant.id,
                    CivilDefenseFormation.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    by_kind = {code: 0 for code in CD_FORMATION_KINDS}
    for formation in formations:
        if formation.kind in by_kind:
            by_kind[formation.kind] += 1
    members_active = int(
        await session.scalar(
            select(func.count())
            .select_from(CivilDefenseFormationMember)
            .where(
                CivilDefenseFormationMember.tenant_id == tenant.id,
                CivilDefenseFormationMember.deleted_at.is_(None),
                CivilDefenseFormationMember.released_on.is_(None),
            )
        )
        or 0
    )
    # Разд. 56.1 «учения»: план-график, просрочки и журнал проведённых за год.
    today = date.today()
    drills = (
        (
            await session.execute(
                select(CivilDefenseDrill).where(
                    CivilDefenseDrill.tenant_id == tenant.id,
                    CivilDefenseDrill.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    return CivilDefenseReadinessRead(
        drills_total=len(drills),
        drills_overdue=sum(
            1 for d in drills if _drill_status(d, today) == "overdue"
        ),
        drills_held_this_year=sum(
            1
            for d in drills
            if d.held_on is not None and d.held_on.year == today.year
        ),
        total_formations=len(formations),
        by_kind=by_kind,
        without_commander=sum(
            1 for f in formations if f.commander_person_id is None
        ),
        members_active=members_active,
    )
