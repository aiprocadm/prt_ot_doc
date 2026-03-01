"""Person CRUD endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, abac
from app.models.models import Company, Person, Position, Tenant, Workplace
from app.repository import list_persons
from app.services.billing import BillingService
from app.schemas.person import PersonCreate, PersonPage, PersonRead, PersonUpdate

router = APIRouter(prefix="/persons", tags=["persons"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_ALLOWED_ROLES = ["admin"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ManagerAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_ALLOWED_ROLES, action="read persons")),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_ALLOWED_ROLES, action="manage persons")),
]


async def _get_company(session: AsyncSession, tenant: Tenant, company_id: str) -> Company:
    stmt = select(Company).where(
        Company.id == company_id,
        Company.tenant_id == tenant.id,
        Company.deleted_at.is_(None),
    )
    company = (await session.execute(stmt)).scalar_one_or_none()
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    return company


async def _get_position(session: AsyncSession, tenant: Tenant, position_id: str) -> Position:
    stmt = select(Position).where(
        Position.id == position_id,
        Position.tenant_id == tenant.id,
        Position.deleted_at.is_(None),
    )
    position = (await session.execute(stmt)).scalar_one_or_none()
    if position is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Position not found")
    return position


async def _get_workplace(
    session: AsyncSession, tenant: Tenant, workplace_id: str
) -> Workplace:
    stmt = select(Workplace).where(
        Workplace.id == workplace_id,
        Workplace.tenant_id == tenant.id,
        Workplace.deleted_at.is_(None),
    )
    workplace = (await session.execute(stmt)).scalar_one_or_none()
    if workplace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workplace not found")
    return workplace


async def _get_person(session: AsyncSession, tenant: Tenant, person_id: str) -> Person:
    stmt = select(Person).where(
        Person.id == person_id,
        Person.tenant_id == tenant.id,
        Person.deleted_at.is_(None),
    )
    person = (await session.execute(stmt)).scalar_one_or_none()
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")
    return person


def _clean_string(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _serialize_records(items):
    if items is None:
        return []
    return [item.model_dump(exclude_unset=True) for item in items]


def _clean_list(values: list[str] | None) -> list[str]:
    if not values:
        return []
    cleaned: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        stripped = value.strip()
        if stripped:
            cleaned.append(stripped)
    return cleaned


@router.get("", response_model=PersonPage)
async def list_persons_endpoint(
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PersonPage:
    persons, total = await list_persons(session, tenant.id, limit=limit, offset=offset)
    return PersonPage(items=persons, total=total)


@router.post("", response_model=PersonRead, status_code=status.HTTP_201_CREATED)
async def create_person_endpoint(
    payload: PersonCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PersonRead:
    await BillingService(session).assert_allowed(tenant, "users.create")
    company = await _get_company(session, tenant, payload.company_id)
    position_id = None
    workplace_id = None
    if payload.position_id is not None:
        position = await _get_position(session, tenant, payload.position_id)
        if position.company_id != company.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Position does not belong to company")
        position_id = position.id
    if payload.workplace_id is not None:
        workplace = await _get_workplace(session, tenant, payload.workplace_id)
        if workplace.company_id != company.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Workplace does not belong to company")
        workplace_id = workplace.id

    person = Person(
        tenant_id=tenant.id,
        company_id=company.id,
        position_id=position_id,
        workplace_id=workplace_id,
        first_name=_clean_string(payload.first_name) or payload.first_name,
        last_name=_clean_string(payload.last_name) or payload.last_name,
        middle_name=_clean_string(payload.middle_name),
        birth_date=payload.birth_date,
        personnel_number=_clean_string(payload.personnel_number),
        hired_at=payload.hired_at,
        qualifications=_serialize_records(payload.qualifications),
        snils=_clean_string(payload.snils),
        passport=_clean_string(payload.passport),
        email=_clean_string(str(payload.email)) if payload.email else None,
        phone=_clean_string(payload.phone),
        current_ppe=_serialize_records(payload.current_ppe),
        working_conditions_class=_clean_string(payload.working_conditions_class),
        hazardous_factors=_clean_list(payload.hazardous_factors),
    )
    session.add(person)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Person already exists") from exc
    await session.commit()
    await session.refresh(person)
    return PersonRead.model_validate(person)


@router.get("/{person_id}", response_model=PersonRead)
async def get_person_endpoint(
    person_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
) -> PersonRead:
    person = await _get_person(session, tenant, person_id)
    return PersonRead.model_validate(person)


@router.patch("/{person_id}", response_model=PersonRead)
async def update_person_endpoint(
    person_id: str,
    payload: PersonUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PersonRead:
    person = await _get_person(session, tenant, person_id)
    data = payload.model_dump(exclude_unset=True)

    target_company = None
    if "company_id" in data:
        if data["company_id"] is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "company_id cannot be null")
        target_company = await _get_company(session, tenant, data["company_id"])
        person.company_id = target_company.id

    company_for_position_id = target_company.id if target_company else person.company_id
    if company_for_position_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Person is not linked to a company")

    if "position_id" in data:
        position_value = data["position_id"]
        if position_value is None:
            person.position_id = None
        else:
            position = await _get_position(session, tenant, position_value)
            if position.company_id != company_for_position_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Position does not belong to company")
            person.position_id = position.id

    if "workplace_id" in data:
        workplace_value = data["workplace_id"]
        if workplace_value is None:
            person.workplace_id = None
        else:
            workplace = await _get_workplace(session, tenant, workplace_value)
            if workplace.company_id != company_for_position_id:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "Workplace does not belong to company"
                )
            person.workplace_id = workplace.id

    text_fields = {
        "first_name": (True, person.first_name),
        "last_name": (True, person.last_name),
        "middle_name": (False, person.middle_name),
        "personnel_number": (False, person.personnel_number),
        "snils": (False, person.snils),
        "passport": (False, person.passport),
        "phone": (False, person.phone),
        "working_conditions_class": (False, person.working_conditions_class),
    }

    for field, (required, _) in text_fields.items():
        if field in data:
            cleaned = _clean_string(data[field])
            if required and cleaned is None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, f"{field} cannot be empty"
                )
            setattr(person, field, cleaned)

    if "birth_date" in data:
        person.birth_date = data["birth_date"]
    if "hired_at" in data:
        person.hired_at = data["hired_at"]
    if "qualifications" in data:
        person.qualifications = _serialize_records(data["qualifications"])
    if "current_ppe" in data:
        person.current_ppe = _serialize_records(data["current_ppe"])
    if "email" in data:
        person.email = _clean_string(str(data["email"])) if data["email"] else None
    if "hazardous_factors" in data:
        person.hazardous_factors = _clean_list(data.get("hazardous_factors"))

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Person already exists") from exc
    await session.refresh(person)
    return PersonRead.model_validate(person)


@router.delete(
    "/{person_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_person_endpoint(
    person_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> None:
    person = await _get_person(session, tenant, person_id)
    if person.deleted_at is None:
        person.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
