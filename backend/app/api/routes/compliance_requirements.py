"""Реестр требований — обязательное ядро арендатора (B.18 разд. 19.2, срез-145).

До среза платформа знала, какие ДОКУМЕНТЫ зависят от акта (связи НПА,
разд. 19.3), но не знала, какие ОБЯЗАННОСТИ из него следуют: «провести
обучение раз в год», «пересмотреть инструкции раз в пять лет». Реестр
требований — эти обязанности как строки данных: откуда, к кому относится,
кто отвечает, как часто, когда крайний срок, чем доказано.

Права — как у связей НПА (``_IMPACT_WRITE_ROLES``): заводят, правят и
закрывают требования admin / owner / ot_specialist. Читают все роли
арендатора, но роли без обзора по арендатору (работник, ученик, бухгалтер
клиента…) видят только требования, за которые отвечают сами: реестр —
картина обязательств всего арендатора, и рядовому сотруднику она ни к чему,
а его собственная обязанность — как раз к чему (см. Центр внимания).

Пути — под ``/compliance/requirements``: ``/obligations`` уже занято
задачами-обязательствами (``Task``), а ``/compliance`` — контрольными
сроками персонала; реестр требований — третий, «нормативный» контур того же
соответствия.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.disciplines import PROCESS_CODES, process_label, process_options
from app.core.role_labels import ROLE_CODES, role_label, role_options
from app.core.security import AccessContext, abac, rbac
from app.core.tenant_validation import TenantContextValidator
from app.domains.npa.requirements import RequirementsService, days_left, is_overdue, today
from app.domains.npa.scope import get_visible_act
from app.models.compliance_requirements import ComplianceRequirement
from app.models.document import Document
from app.models.identity import User
from app.models.master_data import Site
from app.models.models import Tenant
from app.models.npa import NpaClause
from app.schemas.compliance_requirements import (
    ComplianceEvidenceCreate,
    ComplianceEvidenceRead,
    ComplianceRequirementCreate,
    ComplianceRequirementDetail,
    ComplianceRequirementListResponse,
    ComplianceRequirementOptions,
    ComplianceRequirementRead,
    ComplianceRequirementUpdate,
)

router = APIRouter(prefix="/compliance/requirements", tags=["compliance-requirements"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

#: Заводить и закрывать требования — тем же, кто ставит задачи по НПА.
_WRITE_ROLES = ["admin", "owner", "ot_specialist"]

#: Роли с обзором по арендатору: видят реестр целиком. Остальные — только
#: свои (``owner_user_id``). Набор — управленческий read-set компл. сроков
#: плюс эколог (у него свои требования по экологии).
_FULL_READ_ROLES = frozenset(
    {
        "admin",
        "owner",
        "hr",
        "line_manager",
        "manager",
        "ot_pb_lead",
        "ot_head",
        "ot_specialist",
        "pb_engineer",
        "ecologist",
        "accountant",
        "auditor_ro",
    }
)


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


_WriteAccess = Depends(
    abac(_tenant_resource_id, required_roles=_WRITE_ROLES, action="manage compliance requirements")
)


def _role_of(access: AccessContext) -> str:
    role = getattr(access.user, "role", "")
    return str(getattr(role, "value", role))


def _owner_scope(access: AccessContext) -> str | None:
    """None — видит весь реестр; иначе id пользователя, чьи требования показывать.

    Роль с привязкой к компании идёт по личной ветке, как в Центре внимания:
    реестр не умеет сужать по компании, и админ одного клиента арендатора-
    аутсорсера увидел бы обязательства другого.
    """
    if _role_of(access) in _FULL_READ_ROLES and not getattr(access, "company_id", None):
        return None
    return str(access.user.id)


def _read(
    row: ComplianceRequirement,
    refs: dict[str, dict[str, dict[str, Any]]],
    evidence_count: int,
    reference: date,
) -> dict[str, Any]:
    act = refs["acts"].get(row.npa_id or "", {})
    clause = refs["clauses"].get(row.clause_id or "", {})
    owner = refs["users"].get(row.owner_user_id or "", {})
    site = refs["sites"].get(row.site_id or "", {})
    return {
        "id": row.id,
        "code": row.code,
        "title": row.title,
        "description": row.description,
        "npa_id": row.npa_id,
        "npa_code": act.get("code"),
        "npa_title": act.get("title"),
        "clause_id": row.clause_id,
        "clause_code": clause.get("code"),
        "role_code": row.role_code,
        "role_label": role_label(row.role_code),
        "site_id": row.site_id,
        "site_name": site.get("name"),
        "process_code": row.process_code,
        "process_label": process_label(row.process_code),
        "owner_user_id": row.owner_user_id,
        "owner_name": owner.get("name"),
        "periodicity_days": row.periodicity_days,
        "next_due_at": row.next_due_at,
        "last_confirmed_at": row.last_confirmed_at,
        "severity": row.severity,
        "status": row.status,
        "retired_at": row.retired_at,
        "overdue": is_overdue(row, reference),
        "days_left": days_left(row, reference),
        "evidence_count": evidence_count,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


async def _validate_links(session: AsyncSession, tenant_id: str, payload: dict[str, Any]) -> None:
    """Ссылки заявки должны существовать: акт и пункт — в ВИДИМОЙ части реестра,
    площадка (живая, не снесённая) и ответственный — у этого арендатора. Иначе
    404 с понятным словом, а не 500 от внешнего ключа на PostgreSQL и молчание
    на SQLite. Роль — закрытый словарь ``RoleEnum`` (срез-147): выдуманная
    роль отвергается на записи, иначе «к кому относится» было бы свободной
    строкой, по которой ничего не отобрать."""
    role_code = payload.get("role_code")
    if role_code and role_code not in ROLE_CODES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Роли «{role_code}» нет в системе — выберите роль из справочника",
        )
    # Срез-196: процесс — тоже закрытый словарь. Пока он был свободной строкой,
    # «обучение», «Обучение» и «обучение по ОТ» были тремя разными процессами,
    # и сроки требований не попадали ни в один дисциплинарный отчёт.
    process_code = payload.get("process_code")
    if process_code and process_code not in PROCESS_CODES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Процесса «{process_code}» нет в справочнике — выберите из списка",
        )
    npa_id = payload.get("npa_id")
    # Срез-201: «акт есть» перестало быть глобальным вопросом. Чужой локальный
    # приказ для этого арендатора не существует — иначе, заводя требование по
    # подобранному идентификатору, он вычитал бы код и название чужого акта.
    if npa_id and await get_visible_act(session, npa_id, tenant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "NPA act not found")
    clause_id = payload.get("clause_id")
    if clause_id:
        clause = await session.get(NpaClause, clause_id)
        if clause is None or (npa_id and clause.act_id != npa_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "NPA clause not found")
        # Пункт — часть акта, и видимость наследует от него. Без этой проверки
        # `npa_id` можно было просто не присылать, и пункт чужого приказа
        # прошёл бы: его текст виден в требовании.
        if await get_visible_act(session, clause.act_id, tenant_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "NPA clause not found")
    site_id = payload.get("site_id")
    if site_id:
        site = await session.scalar(
            select(Site.id).where(
                Site.id == site_id, Site.tenant_id == tenant_id, Site.deleted_at.is_(None)
            )
        )
        if site is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    owner_user_id = payload.get("owner_user_id")
    if owner_user_id:
        owner = await session.scalar(
            select(User.id).where(User.id == owner_user_id, User.tenant_id == tenant_id)
        )
        if owner is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Owner user not found")


async def _load_visible(
    service: RequirementsService, requirement_id: str, access: AccessContext
) -> ComplianceRequirement:
    """Строка арендатора, видимая пришедшему; чужая или невидимая — 404.

    404, а не 403: подтверждать существование чужого требования нельзя
    (тот же ответ, что у чужого арендатора).
    """
    row = await service.get(requirement_id)
    scope = _owner_scope(access)
    if row is None or (scope is not None and row.owner_user_id != scope):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Requirement not found")
    return row


async def _reload(
    session: AsyncSession, service: RequirementsService, row: ComplianceRequirement
) -> ComplianceRequirement:
    """Перечитать строку после commit — вместе с доказательствами.

    Сессия не сбрасывает объекты при commit, и загруженный до записи список
    ``evidence`` остался бы пустым в ответе «Исполнено».
    """
    # id — до expire: после него любое поле дочитывается синхронно, а в
    # async-сессии это «greenlet_spawn has not been called».
    row_id = row.id
    session.expire(row)
    fresh = await service.get(row_id)
    assert fresh is not None
    return fresh


async def _detail(
    service: RequirementsService, row: ComplianceRequirement, reference: date
) -> ComplianceRequirementDetail:
    refs = await service.references([row])
    titles = await service.document_titles({e.document_id for e in row.evidence if e.document_id})
    evidence = [
        ComplianceEvidenceRead(
            id=item.id,
            requirement_id=item.requirement_id,
            document_id=item.document_id,
            document_title=titles.get(item.document_id or ""),
            note=item.note,
            confirmed_at=item.confirmed_at,
            confirmed_by=item.confirmed_by,
            created_at=item.created_at,
        )
        for item in row.evidence
    ]
    return ComplianceRequirementDetail(
        **_read(row, refs, len(evidence), reference), evidence=evidence
    )


@router.get("", response_model=ComplianceRequirementListResponse)
async def list_requirements(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = Depends(rbac()),
    npa_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    overdue: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ComplianceRequirementListResponse:
    """Реестр требований по НПА страницами (B.18 разд. 19.2, срез-195).

    До этого среза ручка отдавала ВСЮ таблицу требований арендатора на каждое
    открытие экрана, а порядок считался в памяти после выборки — то есть
    страницы были невозможны в принципе.

    Счётчики берутся по ВСЕЙ выборке при тех же фильтрах, а не по выданной
    странице: счётчик по странице — класс ошибки, который в проекте ловили
    дважды, и человек по нему делает ложный вывод «просроченных нет».
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    service = RequirementsService(session, str(tenant.id))
    scope = {
        "npa_id": npa_id,
        "status": status_filter,
        "only_overdue": overdue,
        "owner_user_id": _owner_scope(access),
    }
    rows = await service.list(**scope, limit=limit, offset=offset)
    totals = await service.counts(**scope)
    refs = await service.references(rows)
    counts = await service.evidence_counts(rows)
    reference = today()
    items = [
        ComplianceRequirementRead(**_read(row, refs, counts.get(row.id, 0), reference))
        for row in rows
    ]
    return ComplianceRequirementListResponse(
        items=items,
        total=totals["total"],
        active=totals["active"],
        overdue=totals["overdue"],
        can_manage=_role_of(access) in _WRITE_ROLES,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=ComplianceRequirementDetail, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "compliance_requirement")
async def create_requirement(
    payload: ComplianceRequirementCreate,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = _WriteAccess,
) -> ComplianceRequirementDetail:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    data = payload.model_dump()
    await _validate_links(session, str(tenant.id), data)
    row = ComplianceRequirement(tenant_id=str(tenant.id), status="active", **data)
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        # uq_compliance_requirement_code: код — естественный ключ арендатора.
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Требование с кодом «{payload.code}» уже есть"
        ) from exc
    service = RequirementsService(session, str(tenant.id))
    return await _detail(service, await _reload(session, service, row), today())


@router.get("/options", response_model=ComplianceRequirementOptions)
async def requirement_options(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = _WriteAccess,
) -> ComplianceRequirementOptions:
    """Справочники формы требования — тем, кто требования заводит (срез-147).

    Ответственный, площадка и роль ВЫБИРАЮТСЯ, а не впечатываются. Ручки
    ``/admin/users`` и ``/sites`` — административные (управление доступом и
    объектами) и отвечают специалисту по ОТ 403: без своей ручки поле
    «Ответственный» у него было пустым, а площадку нельзя было выбрать вовсе
    (ограничение среза-145). Срез-196 добавил сюда ПРОЦЕССЫ: до него это была
    свободная строка с подсказкой-жаргоном, и выбрать было не из чего. Отдаётся ровно то, что нужно для выбора: имя и
    роль пользователя, имя площадки с компанией, роли словами — без почты,
    атрибутов и прав. Объявлена раньше ``/{requirement_id}``: иначе слово
    «options» читалось бы как идентификатор требования.
    """
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    service = RequirementsService(session, str(tenant.id))
    return ComplianceRequirementOptions(
        owners=await service.owner_options(),
        sites=await service.site_options(),
        roles=role_options(),
        processes=process_options(),
    )


@router.get("/{requirement_id}", response_model=ComplianceRequirementDetail)
async def get_requirement(
    requirement_id: str,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = Depends(rbac()),
) -> ComplianceRequirementDetail:
    TenantContextValidator.ensure_tenant_context(tenant)
    service = RequirementsService(session, str(tenant.id))
    row = await _load_visible(service, requirement_id, access)
    return await _detail(service, row, today())


@router.patch("/{requirement_id}", response_model=ComplianceRequirementDetail)
@audit_operation("update", "compliance_requirement")
async def update_requirement(
    requirement_id: str,
    payload: ComplianceRequirementUpdate,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = _WriteAccess,
) -> ComplianceRequirementDetail:
    TenantContextValidator.ensure_tenant_context(tenant)
    service = RequirementsService(session, str(tenant.id))
    row = await _load_visible(service, requirement_id, access)
    changes = payload.model_dump(exclude_unset=True)
    await _validate_links(
        session, str(tenant.id), {**changes, "npa_id": changes.get("npa_id", row.npa_id)}
    )
    for field, value in changes.items():
        setattr(row, field, value)
    await session.commit()
    return await _detail(service, await _reload(session, service, row), today())


@router.post(
    "/{requirement_id}/evidence",
    response_model=ComplianceRequirementDetail,
    status_code=status.HTTP_201_CREATED,
)
@audit_operation("confirm", "compliance_requirement")
async def add_evidence(
    requirement_id: str,
    payload: ComplianceEvidenceCreate,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = _WriteAccess,
) -> ComplianceRequirementDetail:
    """«Исполнено»: доказательство записано, контрольная дата сдвинута.

    Ответ — вся строка с доказательствами: витрине после подтверждения нужна
    новая контрольная дата и новый статус, а не только запись доказательства.
    """
    TenantContextValidator.ensure_tenant_context(tenant)
    service = RequirementsService(session, str(tenant.id))
    row = await _load_visible(service, requirement_id, access)
    if not payload.document_id and not (payload.note or "").strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Укажите документ или заметку — чем доказано"
        )
    if payload.document_id:
        document = await session.scalar(
            select(Document.id).where(
                Document.id == payload.document_id, Document.tenant_id == str(tenant.id)
            )
        )
        if document is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    await service.confirm(
        row,
        confirmed_by=str(access.user.id),
        document_id=payload.document_id,
        note=(payload.note or "").strip() or None,
        confirmed_at=payload.confirmed_at,
    )
    await session.commit()
    return await _detail(service, await _reload(session, service, row), today())


@router.post("/{requirement_id}/retire", response_model=ComplianceRequirementDetail)
@audit_operation("retire", "compliance_requirement")
async def retire_requirement(
    requirement_id: str,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = _WriteAccess,
) -> ComplianceRequirementDetail:
    """«Снять с контроля»: акт отменён или процесс закрыт. Удаления нет —
    доказательства нужны на проверке дольше, чем само требование."""
    TenantContextValidator.ensure_tenant_context(tenant)
    service = RequirementsService(session, str(tenant.id))
    row = await _load_visible(service, requirement_id, access)
    if row.status != "retired":
        service.retire(row)
        await session.commit()
    return await _detail(service, await _reload(session, service, row), today())
