"""Person CRUD endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_correlation_id, get_session, get_tenant_record
from app.api.dependencies_managed_client import ClientScopeDep
from app.api.helpers.client_scope import (
    ensure_in_client_scope,
    ensure_writable_client_scope,
    forbid_impersonated_action,
    scope_company_id,
)
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.screen_access import screen_roles
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.db.session import rearm_session_tenant_context
from app.models.models import Company, Person, Position, Tenant, Workplace
from app.modules.privacy.service import PdnAccessJournal
from app.repository import list_persons
from app.schemas.person import PersonCreate, PersonPage, PersonRead, PersonUpdate
from app.services.billing import BillingService

router = APIRouter(prefix="/persons", tags=["persons"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

# Роли берутся из единой карты прав экрана (core/screen_access): пункт меню
# виден ровно тем, кого пускает ручка — иначе человек видит раздел и получает
# 403 (docs/audit/ACCESS_MENU_VS_API.md, сторож tests/test_menu_matches_api.py).
_PERSON_READ_ROLES = list(screen_roles("person.view"))
_PERSON_WRITE_ROLES = list(screen_roles("person.create"))


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ManagerAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_PERSON_READ_ROLES, action="read persons")),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_PERSON_WRITE_ROLES, action="manage persons")),
]


def _person_bad_request(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=api_problem_detail(
            code="PERSON_VALIDATION_ERROR", message=message, error_type="persons"
        ),
    )


def _person_unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(
            code="PERSON_VALIDATION_ERROR", message=message, error_type="persons"
        ),
    )


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


async def _get_workplace(session: AsyncSession, tenant: Tenant, workplace_id: str) -> Workplace:
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


# Поля Person, которые считаются персональными данными субъекта (SEC-66).
# Их изменение попадает в журнал доступа к ПДн, а у обезличенного субъекта
# запрещено. Держим рядом с обработчиком: список читается вместе с валидацией.
PDN_PII_FIELDS: frozenset[str] = frozenset(
    {
        "first_name",
        "last_name",
        "middle_name",
        "birth_date",
        "email",
        "phone",
        "personnel_number",
        "snils",
        "passport",
        "hired_at",
        "qualifications",
        "current_ppe",
    }
)


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
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    scope: ClientScopeDep,
    correlation_id: str = Depends(get_correlation_id),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, max_length=200, description="Поиск по ФИО / таб. номеру"),
    # Умолчание — обычный ``None``, а не объект ``Query``: этот роут зовут
    # НАПРЯМУЮ из тестов области видимости, и объект ``Query`` уехал бы в
    # запрос как значение параметра («type 'Query' is not supported»).
    company_id: Annotated[
        str | None,
        Query(min_length=1, max_length=36, description="Только сотрудники этой организации"),
    ] = None,
) -> PersonPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)

    # Работа «от имени клиента» (BIZ-49 срез-9): область видимости сужается до
    # его организации. Если данных клиента в этом контуре нет — список пуст,
    # но НИКОГДА не «весь арендатор»: иначе под вывеской «вы работаете от
    # имени ООО Ромашка» специалист увидит сотрудников всех остальных клиентов.
    if scope is not None and not scope.visible:
        persons, total = [], 0
    else:
        persons, total = await list_persons(
            session,
            tenant.id,
            limit=limit,
            offset=offset,
            q=q,
            # Фильтр СУЖАЕТ, но никогда не расширяет: в контексте «от имени
            # клиента» область уже ограничена его организацией, и запрос с
            # чужим company_id обязан дать пустой список, а не чужих людей.
            company_id=_narrow_company(scope_company_id(scope), company_id),
        )
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=persons,
        scalars=[
            ("total", total),
            ("limit", limit),
            ("offset", offset),
            ("q", q or ""),
            # Без этого два разных фильтра по организации дали бы ОДИН ETag, и
            # второй запрос получил бы 304 со списком чужой организации.
            ("company", company_id or ""),
            # Иначе кэш, набранный вне контекста, вернулся бы 304-м ответом
            # уже внутри контекста клиента — со всем арендатором внутри.
            ("managed_client", scope.client_id if scope else ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return PersonPage(items=persons, total=total)


def _narrow_company(scope_company: str | None, requested: str | None) -> str | None:
    """Пересечение области видимости и запрошенного фильтра.

    Мастер комплекта (BIZ-50) выбирает людей ОДНОЙ организации: генерация
    отвергает сотрудника из другой (400), и предлагать таких в списке значит
    вести человека в тупик.

    Фильтровать на стороне интерфейса было нельзя: список постраничный, и
    сотрудники за пределами страницы молча не попали бы в выбор — ровно тот
    случай, когда экран выглядит рабочим, а данные теряются.
    """

    if scope_company and requested and scope_company != requested:
        # Осознанно пустой список, а не «покажем область видимости»: иначе
        # ответ не соответствовал бы заданному вопросу.
        return "__none__"
    return requested or scope_company


@router.post("", response_model=PersonRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "person")
async def create_person_endpoint(
    payload: PersonCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
    scope: ClientScopeDep,
    correlation_id: str = Depends(get_correlation_id),
) -> PersonRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    # Не использовать users.create: квота max_users считает записи User, а не Person — блокировало HR-сценарии.
    await BillingService(session).assert_allowed(tenant, "persons.create")
    ensure_writable_client_scope(scope)
    company = await _get_company(session, tenant, payload.company_id)
    # В контексте клиента заводить можно ТОЛЬКО его сотрудников. Иначе самая
    # дорогая ошибка аутсорсера — человек, заведённый не в ту организацию, —
    # совершается именно тогда, когда специалист уверен, что работает «от
    # имени» нужного клиента.
    ensure_in_client_scope(scope, company.id, entity="Company")
    position_id = None
    workplace_id = None
    if payload.position_id is not None:
        position = await _get_position(session, tenant, payload.position_id)
        if position.company_id != company.id:
            raise _person_bad_request("Position does not belong to company")
        position_id = position.id
    if payload.workplace_id is not None:
        workplace = await _get_workplace(session, tenant, payload.workplace_id)
        if workplace.company_id != company.id:
            raise _person_bad_request("Workplace does not belong to company")
        workplace_id = workplace.id

    person = Person(
        tenant_id=tenant.id,
        company_id=company.id,
        position_id=position_id,
        workplace_id=workplace_id,
        first_name=_clean_string(payload.first_name) or payload.first_name,
        last_name=_clean_string(payload.last_name) or payload.last_name,
        middle_name=_clean_string(payload.middle_name),
        position_title=_clean_string(payload.position_title),
        birth_date=payload.birth_date,
        personnel_number=_clean_string(payload.personnel_number),
        hired_at=payload.hired_at,
        qualifications=_serialize_records(payload.qualifications),
        snils=_clean_string(payload.snils),
        passport=_clean_string(payload.passport),
        email=_clean_string(str(payload.email)) if payload.email else None,
        phone=_clean_string(payload.phone),
        employment_status=payload.employment_status,
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
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(person)
    return PersonRead.model_validate(person)


@router.get("/{person_id}", response_model=PersonRead)
async def get_person_endpoint(
    person_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    scope: ClientScopeDep,
    correlation_id: str = Depends(get_correlation_id),
) -> PersonRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    person = await _get_person(session, tenant, person_id)
    # Чужой человек — 404, а не 403: «доступ запрещён» подтвердило бы, что
    # такая запись есть, и перебором идентификаторов раскрыло бы состав
    # организаций других клиентов аутсорсера.
    ensure_in_client_scope(scope, person.company_id, entity="Person")
    return PersonRead.model_validate(person)


@router.patch("/{person_id}", response_model=PersonRead)
@audit_operation("update", "person")
async def update_person_endpoint(
    person_id: str,
    payload: PersonUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
    scope: ClientScopeDep,
    correlation_id: str = Depends(get_correlation_id),
) -> PersonRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    person = await _get_person(session, tenant, person_id)
    ensure_writable_client_scope(scope)
    ensure_in_client_scope(scope, person.company_id, entity="Person")
    data = payload.model_dump(exclude_unset=True)

    # SEC-66 (разд. 66.2): обезличивание необратимо. Правка ПДн обезличенного
    # субъекта вернула бы идентификаторы обратно, обесценив «право на удаление».
    touched_pii = sorted(set(data) & set(PDN_PII_FIELDS))
    if person.anonymized_at is not None and touched_pii:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=api_problem_detail(
                code="PDN_SUBJECT_ANONYMIZED",
                message="Personal data of an anonymized subject cannot be restored",
                error_type="privacy",
            ),
        )
    pii_before = {field: getattr(person, field, None) for field in touched_pii}

    target_company = None
    if "company_id" in data:
        if data["company_id"] is None:
            raise _person_unprocessable("company_id cannot be null")
        target_company = await _get_company(session, tenant, data["company_id"])
        # Перенос человека НАРУЖУ контекста клиента запрещён: иначе работа «от
        # имени» становится способом увести сотрудника в чужую организацию.
        ensure_in_client_scope(scope, target_company.id, entity="Company")
        person.company_id = target_company.id

    company_for_position_id = target_company.id if target_company else person.company_id
    if company_for_position_id is None:
        raise _person_bad_request("Person is not linked to a company")

    if "position_id" in data:
        position_value = data["position_id"]
        if position_value is None:
            person.position_id = None
        else:
            position = await _get_position(session, tenant, position_value)
            if position.company_id != company_for_position_id:
                raise _person_bad_request("Position does not belong to company")
            person.position_id = position.id

    if "workplace_id" in data:
        workplace_value = data["workplace_id"]
        if workplace_value is None:
            person.workplace_id = None
        else:
            workplace = await _get_workplace(session, tenant, workplace_value)
            if workplace.company_id != company_for_position_id:
                raise _person_bad_request("Workplace does not belong to company")
            person.workplace_id = workplace.id

    text_fields = {
        "first_name": (True, person.first_name),
        "last_name": (True, person.last_name),
        "middle_name": (False, person.middle_name),
        "position_title": (False, person.position_title),
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
                raise _person_unprocessable(f"{field} cannot be empty")
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
    if "employment_status" in data:
        person.employment_status = data["employment_status"]

    # SEC-66 (разд. 66.2 «уточнение/исправление»): журнал ведётся по СУБЪЕКТУ, а
    # общий audit_log — по объекту действия, поэтому одного его мало. Пишем только
    # при фактическом изменении: запись «правил, но ничего не изменил» зашумила бы
    # выдачу субъекту.
    changed = [f for f in touched_pii if getattr(person, f, None) != pii_before[f]]
    if changed:
        await PdnAccessJournal(session).record(
            tenant_id=str(tenant.id),
            subject_person_id=str(person.id),
            action="rectify",
            actor_user_id=str(access.user.id) if access.user else None,
            actor_email=getattr(access.user, "email", None),
            purpose=f"changed: {', '.join(changed)}",
            request_id=correlation_id,
        )

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Person already exists") from exc
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(person)
    return PersonRead.model_validate(person)


@router.delete(
    "/{person_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
@audit_operation("delete", "person")
async def delete_person_endpoint(
    person_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
    scope: ClientScopeDep,
    correlation_id: str = Depends(get_correlation_id),
) -> None:
    TenantContextValidator.ensure_tenant_context(tenant)

    person = await _get_person(session, tenant, person_id)
    ensure_in_client_scope(scope, person.company_id, entity="Person")
    # Доп. №3 разд. 63.2: удаление данных запрещено имперсонатору ДАЖE в
    # контексте клиента. Убрать чужого сотрудника «от имени клиента» — самое
    # неприятное из возможного: следов правки нет, есть только пропавший
    # человек. Первое применение запрета; общий список запретов — срез-10.
    forbid_impersonated_action(scope, action="удаление сотрудника")
    if person.deleted_at is None:
        person.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
