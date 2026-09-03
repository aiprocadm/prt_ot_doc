"""Стажировка на рабочем месте — ядровые ручки (требование Доп. №1 разд. 56.2).

ПОЧЕМУ РУЧКИ В ЯДРЕ, А НЕ В КОНТУРЕ БДД. Требование пришло из разд. 56.2
(«инструктажи и СТАЖИРОВКИ водителей»), но вещь не водительская: комплект
документов печатает «Стажировка: N смен» в первичном инструктаже НОВОГО
РАБОТНИКА, то есть по охране труда и любому рабочему. Своя ручка внутри БДД
означала бы второй реестр того же самого, как только понадобится стажировка
стропальщика.

Приём канонический — четвёртый случай подряд: общая сущность в ядре +
разметка дисциплиной (виды инструктажа 54.1, области аттестации 54.2 и 56.2,
дисциплина курса 56.1). Контур дисциплины отбирает СВОИ записи.

Экрана у стажировок пока нет — как не было у ядровых аттестаций до разд. 54.2:
записи видны через API и через счётчики контура дисциплины. Это названо в
handoff как следующий шаг, а не спрятано.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.dependencies import get_session, get_tenant_record
from app.core.disciplines import DISCIPLINE_TITLES, Discipline
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.master_data import Person
from app.models.models import Tenant
from app.models.training import INTERNSHIP_STATUSES, Internship
from app.schemas.internships import (
    InternshipCreate,
    InternshipPage,
    InternshipRead,
    InternshipUpdate,
)
from app.services.audit import AuditService, field_level_diff

router = APIRouter(tags=["internships"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_READ_ROLES = ["admin", "owner", "hr", "line_manager", "ot_pb_lead", "ot_specialist"]
_WRITE_ROLES = ["admin", "owner", "hr", "line_manager", "ot_pb_lead", "ot_specialist"]

#: коды дисциплин словами — берутся из ОБЩЕГО словаря продукта, своей копии
#: здесь нет: две копии разошлись бы на первой новой дисциплине
_DISCIPLINE_CODES = {d.value: DISCIPLINE_TITLES[d] for d in Discipline}


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ReaderAccess = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id,
            required_roles=_READ_ROLES,
            action="read internships",
        )
    ),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id,
            required_roles=_WRITE_ROLES,
            action="manage internships",
        )
    ),
]


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(
            code="INTERNSHIP_INVALID", message=message, error_type="internships"
        ),
    )


def _person_name(person: Person | None) -> str:
    if person is None:
        return ""
    return " ".join(
        part
        for part in (person.last_name, person.first_name, person.middle_name)
        if part
    )


def _shifts_remaining(record: Internship) -> int:
    """Сколько смен осталось до плана. Считается, а не хранится."""

    return max(0, record.planned_shifts - record.completed_shifts)


def _completed_short(record: Internship) -> bool:
    """Стажировка ЗАВЕРШЕНА, а смен меньше плана.

    Самое ценное, что тут можно показать: формально закрытая стажировка,
    которой по сменам не было. ГРАНИЦА: это ФАКТ расхождения плана и факта, а
    НЕ вердикт «допуск незаконен» — платформа не решает, сколько смен нужно.
    """

    return record.status == "completed" and record.completed_shifts < record.planned_shifts


def _read(record: Internship, trainee: Person | None, mentor: Person | None) -> InternshipRead:
    return InternshipRead(
        id=record.id,
        person_id=record.person_id,
        person_name=_person_name(trainee),
        mentor_person_id=record.mentor_person_id,
        # пусто — наставник НЕ НАЗНАЧЕН, а не «неизвестен»
        mentor_name=_person_name(mentor) if mentor is not None else None,
        discipline=record.discipline,
        discipline_label=(
            _DISCIPLINE_CODES.get(record.discipline) if record.discipline else None
        ),
        subject=record.subject,
        planned_shifts=record.planned_shifts,
        completed_shifts=record.completed_shifts,
        shifts_remaining=_shifts_remaining(record),
        completed_short=_completed_short(record),
        started_on=record.started_on,
        finished_on=record.finished_on,
        status=record.status,
        status_label=INTERNSHIP_STATUSES.get(record.status, record.status),
        notes=record.notes,
    )


def _validate(
    *, discipline: str | None, status_value: str | None, planned: int | None, completed: int | None
) -> None:
    if discipline is not None and discipline not in _DISCIPLINE_CODES:
        raise _unprocessable(
            f"Неизвестная дисциплина {discipline!r}; допустимые: "
            f"{', '.join(_DISCIPLINE_CODES)}"
        )
    if status_value is not None and status_value not in INTERNSHIP_STATUSES:
        raise _unprocessable(
            f"Неизвестное состояние стажировки {status_value!r}; допустимые: "
            f"{', '.join(INTERNSHIP_STATUSES)}"
        )


async def _ensure_person(session: AsyncSession, tenant: Tenant, person_id: str) -> Person:
    """Человек обязан быть СВОИМ и живым: стажировка людей не заводит."""

    person = (
        await session.execute(
            select(Person).where(
                Person.id == person_id,
                Person.tenant_id == tenant.id,
                Person.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if person is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="PERSON_NOT_FOUND", message="Person not found", error_type="internships"
            ),
        )
    return person


async def _load(session: AsyncSession, tenant: Tenant, record_id: str):
    Mentor = aliased(Person)
    stmt = (
        select(Internship, Person, Mentor)
        .join(Person, Person.id == Internship.person_id)
        .outerjoin(Mentor, Mentor.id == Internship.mentor_person_id)
        .where(
            Internship.id == record_id,
            Internship.tenant_id == tenant.id,
            Internship.deleted_at.is_(None),
        )
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="INTERNSHIP_NOT_FOUND",
                message="Internship not found",
                error_type="internships",
            ),
        )
    return row


@router.get("/internships", response_model=InternshipPage)
async def list_internships(
    tenant: TenantDep,
    session: SessionDep,
    access: ReaderAccess,
    person_id: str | None = Query(default=None),
    discipline: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> InternshipPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    Mentor = aliased(Person)
    stmt = (
        select(Internship, Person, Mentor)
        .join(Person, Person.id == Internship.person_id)
        .outerjoin(Mentor, Mentor.id == Internship.mentor_person_id)
        .where(Internship.tenant_id == tenant.id, Internship.deleted_at.is_(None))
    )
    if person_id:
        stmt = stmt.where(Internship.person_id == person_id)
    if discipline:
        stmt = stmt.where(Internship.discipline == discipline)
    if status_filter:
        stmt = stmt.where(Internship.status == status_filter)
    stmt = stmt.order_by(Internship.started_on.desc().nullslast())
    total = int(
        await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )
    rows = (await session.execute(stmt.offset(offset).limit(limit))).all()
    return InternshipPage(
        items=[_read(record, trainee, mentor) for record, trainee, mentor in rows],
        total=total,
    )


@router.post(
    "/internships", response_model=InternshipRead, status_code=status.HTTP_201_CREATED
)
async def create_internship(
    request: Request,
    payload: InternshipCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> InternshipRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _validate(
        discipline=payload.discipline,
        status_value=payload.status,
        planned=payload.planned_shifts,
        completed=payload.completed_shifts,
    )
    trainee = await _ensure_person(session, tenant, payload.person_id)
    mentor = None
    if payload.mentor_person_id:
        # НАСТАВНИК НЕ МОЖЕТ БЫТЬ СТАЖЁРОМ. Это не педантизм: стажировка «сам у
        # себя» это либо опечатка, либо приписка, и в обоих случаях запись
        # означает, что стажировки не было.
        if payload.mentor_person_id == payload.person_id:
            raise _unprocessable("Наставник не может быть стажёром: это одна и та же запись")
        mentor = await _ensure_person(session, tenant, payload.mentor_person_id)

    record = Internship(
        tenant_id=str(tenant.id),
        person_id=trainee.id,
        mentor_person_id=mentor.id if mentor else None,
        discipline=payload.discipline or None,
        subject=(payload.subject or None),
        planned_shifts=payload.planned_shifts,
        completed_shifts=payload.completed_shifts,
        started_on=payload.started_on,
        finished_on=payload.finished_on,
        status=payload.status,
        notes=(payload.notes or None),
    )
    session.add(record)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="Internship",
        object_id=record.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"fields": {"id": {"before": None, "after": record.id}}},
        details={"entity": "Internship", "person_id": record.person_id},
    )
    await session.commit()
    row = await _load(session, tenant, record.id)
    return _read(*row)


@router.patch("/internships/{internship_id}", response_model=InternshipRead)
async def update_internship(
    request: Request,
    internship_id: str,
    payload: InternshipUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> InternshipRead:
    """Правка: наставник, смены, сроки, состояние.

    СТАЖЁРА СМЕНИТЬ НЕЛЬЗЯ — поля для этого нет: это стажировка другого
    человека, и переписать на него чужие смены значило бы приписать ему
    чужой опыт.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    record, _, _ = await _load(session, tenant, internship_id)
    data = payload.model_dump(exclude_unset=True)
    _validate(
        discipline=data.get("discipline"),
        status_value=data.get("status"),
        planned=data.get("planned_shifts"),
        completed=data.get("completed_shifts"),
    )
    if data.get("mentor_person_id"):
        if data["mentor_person_id"] == record.person_id:
            raise _unprocessable("Наставник не может быть стажёром: это одна и та же запись")
        await _ensure_person(session, tenant, str(data["mentor_person_id"]))

    before = {
        "discipline": str(record.discipline),
        "status": record.status,
        "planned_shifts": str(record.planned_shifts),
        "completed_shifts": str(record.completed_shifts),
    }
    for field in (
        "discipline",
        "subject",
        "planned_shifts",
        "completed_shifts",
        "started_on",
        "finished_on",
        "status",
        "notes",
    ):
        if data.get(field) is not None:
            setattr(record, field, data[field])
    # снять наставника и разметку МОЖНО: ошибочную привязку надо уметь отменить
    for field in ("mentor_person_id", "discipline"):
        if field in data and data[field] is None:
            setattr(record, field, None)
    await session.flush()
    if data.get("mentor_person_id"):
        record.mentor_person_id = str(data["mentor_person_id"])
        await session.flush()
    after = {
        "discipline": str(record.discipline),
        "status": record.status,
        "planned_shifts": str(record.planned_shifts),
        "completed_shifts": str(record.completed_shifts),
    }
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="Internship",
        object_id=record.id,
        user_id=access.user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(before, after),
        details={"entity": "Internship"},
    )
    await session.commit()
    row = await _load(session, tenant, record.id)
    return _read(*row)
