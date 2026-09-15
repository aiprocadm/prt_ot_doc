"""Реестр нормативных актов: чтение для всех, ведение — владельцу платформы.

Связи акта с документами арендатора (``NPABinding``) — уже арендаторские: их
заводит и снимает тот, кто вправе ставить задачи по оценке влияния
(``_IMPACT_WRITE_ROLES``). До среза-142 связи заводить было нечем, и оценка
влияния считала по пустой таблице.

Срез-144 (разд. 19.4, «уведомить → задачи → контроль»): связь помнит, по какой
редакции её сверяли (``reviewed_revision_id``). Пока в реестре действует та же
редакция — связь актуальна; вступила новая — связь «не пересмотрена»: попадает
в Центр внимания арендатора, считается в задачи актуализации и ждёт кнопки
«Пересмотрено» (``POST .../bindings/{id}/review``). Так владелец платформы,
заводя редакцию в общий реестр, ничего не пишет в арендаторские таблицы —
а арендатор всё равно узнаёт об изменении при следующем же входе.

Реестр общий (``NpaAct`` — SharedModel, без tenant_id): один и тот же приказ
Минтруда действует на всех арендаторов. Поэтому заводить акты и редакции
может только владелец платформы — тот же гейт, что у кабинета арендаторов
(``_require_managing_admin``). До среза-141 писать в реестр было некому вовсе:
``GET /npa`` отдавал пустой список всегда, а экран НПА предлагал «добавить
или импортировать» акты, не имея ни одной ручки для этого.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_session, get_tenant_record
from app.api.routes.platform_tenants import _require_managing_admin
from app.core.audit_decorator import audit_operation
from app.core.role_labels import ROLE_CODES, role_label
from app.core.security import abac, rbac
from app.core.tenant_validation import TenantContextValidator
from app.domains.npa.impact import NpaImpactService
from app.domains.npa.revision_diff import diff_clauses
from app.domains.npa.scope import (
    REGISTRY_SCOPE,
    find_act_by_code,
    get_visible_act,
    registry_first,
    scope_of,
    scope_title,
    visible_acts,
)
from app.models.document import Document
from app.models.master_data import Site
from app.models.models import NPABinding, Tenant
from app.models.npa import NpaAct, NpaClause, NpaRevision, NpaRevisionClause
from app.models.packages import DocumentPack
from app.models.templates import TemplateVersion
from app.schemas.npa import (
    NpaActCreate,
    NpaActListResponse,
    NpaActRead,
    NpaBindingContext,
    NpaBindingCreate,
    NpaBindingRead,
    NpaClauseRead,
    NpaRevisionCreate,
    NpaRevisionRead,
)

router = APIRouter(tags=["npa"])
_optional_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# NPA reads (`GET /npa*`) stay authn-only — normative acts are reference data. Creating
# update tasks from an act's impact writes tenant-wide task rows -> DOC_WRITE (mirrors
# the export/report write set: admin/owner/ot_specialist).
_IMPACT_WRITE_ROLES = ["admin", "owner", "ot_specialist"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


def _can_manage(credentials: HTTPAuthorizationCredentials | None, tenant: Tenant) -> bool:
    """Тот же вопрос, что задаёт гейт записи, — но ответом «да/нет», без отказа.

    Список читают все, а кнопку «Добавить акт» должен видеть только тот, кому
    ручка записи ответит 201. Считать это на витрине по роли нельзя: право
    зависит ещё и от того, управляющий ли арендатор, — а это знает только
    бэкенд (``settings.managing_tenant_slug``).
    """

    try:
        _require_managing_admin(credentials, tenant)
    except HTTPException:
        return False
    return True


def _require_act_author(
    credentials: HTTPAuthorizationCredentials | None, tenant: Tenant, act: NpaAct
) -> None:
    """Вести акт вправе тот, чей это акт (срез-201).

    У федерального акта хозяин — владелец платформы: редакция общего приказа
    меняет правила для всех арендаторов сразу. У собственного акта арендатора
    хозяин — он сам, и сюда доходят только акты, уже прошедшие фильтр
    видимости: чужой локальный акт до этой строки не доживает — он отвечен
    как «нет такого». Роль проверена зависимостью ручки.
    """

    if act.owner_tenant_id is None:
        _require_managing_admin(credentials, tenant)


def _act_read(act: NpaAct) -> NpaActRead:
    """Ответ про акт всегда несёт свой ящик — и кодом, и словами."""

    read = NpaActRead.model_validate(act, from_attributes=True)
    return read.model_copy(update={"scope": scope_of(act), "scope_title": scope_title(act)})


@router.get("/npa", response_model=NpaActListResponse)
async def list_npa(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    access=Depends(rbac()),
) -> NpaActListResponse:
    _ = access  # enforce auth
    # Срез-201: список — общий реестр ПЛЮС собственные акты этого арендатора.
    # Чужие локальные сюда не попадают ни при каких правах.
    stmt = (
        visible_acts(str(tenant.id))
        .options(selectinload(NpaAct.clauses))
        .order_by(registry_first(), NpaAct.code)
    )
    acts = (await session.execute(stmt)).scalars().unique().all()
    # Право «завести свой акт» шире права «править общий реестр»: его имеет
    # любой арендатор с ролью, ведущей записи по НПА.
    my_roles = set(session.info.get("current_user_roles") or [])
    return NpaActListResponse(
        items=[_act_read(act) for act in acts],
        can_manage=_can_manage(credentials, tenant),
        can_create_own=bool(my_roles & set(_IMPACT_WRITE_ROLES)),
    )


@router.post("/npa", response_model=NpaActRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "npa_act")
async def create_npa_act(
    payload: NpaActCreate,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    access=Depends(
        abac(
            _tenant_resource_id,
            required_roles=_IMPACT_WRITE_ROLES,
            action="create npa act",
        )
    ),
) -> NpaActRead:
    """Срез-141: точка входа в реестр. Срез-201: реестров стало два.

    ``scope="registry"`` — общий реестр платформы: федеральный приказ действует
    на всех, поэтому писать туда вправе только владелец платформы.
    ``scope="own"`` — собственный акт арендатора (приказ по организации,
    инструкция): его видит и ведёт только он сам.

    Ящик называет заявитель, а не роль угадывает за него. «Завести федеральный
    акт» и «завести свой приказ» — разные поступки с разной ценой ошибки, и
    молчаливый выбор по правам однажды записал бы приказ одной организации в
    общий реестр для всех.
    """

    _ = access
    owner_tenant_id: str | None
    if payload.scope == REGISTRY_SCOPE:
        _require_managing_admin(credentials, tenant)
        owner_tenant_id = None
    else:
        TenantContextValidator.ensure_tenant_context(tenant)
        owner_tenant_id = str(tenant.id)
    duplicate = await find_act_by_code(session, payload.code, owner_tenant_id)
    if duplicate is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Акт с таким кодом уже есть в реестре")
    act = NpaAct(
        owner_tenant_id=owner_tenant_id,
        code=payload.code,
        title=payload.title,
        edition=payload.edition,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
    )
    act.clauses.extend(NpaClause(code=clause.code, text=clause.text) for clause in payload.clauses)
    session.add(act)
    try:
        await session.commit()
    except IntegrityError as exc:
        # Гонка двух одинаковых заявок: проверка выше её не видит, уникальный
        # индекс — видит. Ответ тот же, что и без гонки.
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Акт с таким кодом уже есть в реестре"
        ) from exc
    await session.refresh(act, attribute_names=["clauses"])
    return _act_read(act)


@router.post(
    "/npa/{act_id}/revisions",
    response_model=NpaRevisionRead,
    status_code=status.HTTP_201_CREATED,
)
@audit_operation("create", "npa_revision")
async def create_npa_revision(
    act_id: str,
    payload: NpaRevisionCreate,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    access=Depends(
        abac(
            _tenant_resource_id,
            required_roles=_IMPACT_WRITE_ROLES,
            action="create npa revision",
        )
    ),
) -> NpaRevisionRead:
    """Срез-141: новая редакция акта — её и читает оценка влияния.

    Срез-201: редакцию ведёт тот, чей это акт. У федерального — владелец
    платформы, у собственного приказа арендатора — сам арендатор.
    """

    _ = access
    act = await get_visible_act(session, act_id, str(tenant.id))
    if act is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "NPA act not found")
    _require_act_author(credentials, tenant, act)
    duplicate = await session.scalar(
        select(NpaRevision.id).where(
            NpaRevision.act_id == act_id, NpaRevision.revision_code == payload.revision_code
        )
    )
    if duplicate is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Редакция с таким кодом у акта уже есть")
    revision = NpaRevision(
        act_id=act.id,
        revision_code=payload.revision_code,
        title=payload.title,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        change_summary=payload.change_summary,
    )
    session.add(revision)
    await session.flush()
    # Срез-202: текст редакции. Пунктов может не быть вовсе — редакцию часто
    # заводят заранее, зная только дату. Копировать сюда текущий текст акта
    # НЕЛЬЗЯ: редакция описывает будущий текст, и копия сегодняшнего дала бы
    # дифф «изменений нет» — правдоподобное значение вместо пропущенного.
    for clause in payload.clauses or ():
        session.add(NpaRevisionClause(revision_id=revision.id, code=clause.code, text=clause.text))
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Редакция с таким кодом у акта уже есть"
        ) from exc
    await session.refresh(revision)
    return _revision_read(revision, await _revision_clauses(session, [revision.id]))


async def _revision_clauses(
    session: AsyncSession, revision_ids: list[str]
) -> dict[str, list[NpaRevisionClause]]:
    """Тексты редакций одним запросом.

    Возвращает ТОЛЬКО те редакции, у которых снимок есть: отсутствие ключа и
    пустой список — разные ответы, и различать их обязан уже вызывающий.
    """

    if not revision_ids:
        return {}
    rows = (
        (
            await session.execute(
                select(NpaRevisionClause)
                .where(NpaRevisionClause.revision_id.in_(revision_ids))
                .order_by(NpaRevisionClause.code)
            )
        )
        .scalars()
        .all()
    )
    grouped: dict[str, list[NpaRevisionClause]] = {}
    for row in rows:
        grouped.setdefault(row.revision_id, []).append(row)
    return grouped


def _revision_read(
    revision: NpaRevision, clauses_by_revision: dict[str, list[NpaRevisionClause]]
) -> NpaRevisionRead:
    clauses = clauses_by_revision.get(revision.id)
    read = NpaRevisionRead.model_validate(revision, from_attributes=True)
    return read.model_copy(
        update={
            "has_text": clauses is not None,
            "clauses": [
                NpaClauseRead(id=row.id, code=row.code, text=row.text) for row in clauses or ()
            ],
        }
    )


@router.get("/npa/{act_id}/revisions/diff")
async def compare_npa_revisions(
    act_id: str,
    session: SessionDep,
    base: str = Query(description="От какой редакции считаем изменения"),
    target: str = Query(description="К какой редакции считаем изменения"),
    tenant: Tenant = Depends(get_tenant_record),
    access=Depends(rbac()),
) -> dict:
    """Что изменилось между двумя редакциями акта (срез-202, разд. 19.4).

    Читать может любой, кому виден акт: «что изменилось в законе» — это и есть
    то, ради чего реестр заводили, а не привилегия. Запись редакций осталась за
    тем, чей это акт.

    Порядок редакций НЕ подставляется за человека: он спрашивает «что стало с
    текстом, когда перешли от A к B», и поменять A и B местами значило бы
    ответить на другой вопрос — добавленные пункты стали бы исключёнными.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    act = await get_visible_act(session, act_id, str(tenant.id))
    if act is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "NPA act not found")
    revisions = {
        row.id: row
        for row in (
            (
                await session.execute(
                    select(NpaRevision).where(
                        NpaRevision.act_id == act_id, NpaRevision.id.in_([base, target])
                    )
                )
            )
            .scalars()
            .all()
        )
    }
    # Чужая редакция (или редакция другого акта) — «нет такой», а не «пустой
    # дифф»: иначе по ответу можно было бы перебирать идентификаторы.
    missing = [rid for rid in (base, target) if rid not in revisions]
    if missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "NPA revision not found")
    texts = await _revision_clauses(session, [base, target])
    result = diff_clauses(
        {row.code: row.text for row in texts[base]} if base in texts else None,
        {row.code: row.text for row in texts[target]} if target in texts else None,
    )
    payload = result.as_dict()
    payload["base"] = _revision_read(revisions[base], texts).model_dump(mode="json")
    payload["target"] = _revision_read(revisions[target], texts).model_dump(mode="json")
    return payload


@router.get("/npa/{act_id}")
async def get_npa_detail(
    act_id: str,
    session: SessionDep,
    revision_id: str | None = Query(default=None),
    tenant: Tenant = Depends(get_tenant_record),
    access=Depends(rbac()),
) -> dict:
    TenantContextValidator.ensure_tenant_context(tenant)

    _ = access
    payload = await NpaImpactService(session, str(tenant.id)).detail(
        act_id, revision_id=revision_id
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="NPA act not found")
    return payload


@router.post("/npa/{act_id}/impact/tasks")
@audit_operation("create_tasks", "npa_impact")
async def create_npa_update_tasks(
    act_id: str,
    session: SessionDep,
    revision_id: str | None = Query(default=None),
    tenant: Tenant = Depends(get_tenant_record),
    access=Depends(
        abac(
            _tenant_resource_id,
            required_roles=_IMPACT_WRITE_ROLES,
            action="create npa update tasks",
        )
    ),
) -> dict:
    TenantContextValidator.ensure_tenant_context(tenant)

    tasks = await NpaImpactService(session, str(tenant.id)).create_update_tasks(
        act_id, getattr(access.user, "id", None), revision_id=revision_id
    )
    await session.commit()
    return {
        "created": len(tasks),
        "items": [{"id": item.id, "title": item.title} for item in tasks],
    }


async def _binding_target_exists(
    session: AsyncSession, tenant_id: str, payload: NpaBindingCreate
) -> str | None:
    """Проверить, что цель связи существует у ЭТОГО арендатора.

    Возвращает ``template_version_id`` для связи с версией шаблона (столбец
    остался с начальной схемы, его читает ``TemplateVersion.npa_bindings``),
    ``""`` для остальных живых целей и ``None``, если цели нет.
    """
    if payload.entity_type == "document":
        row = await session.scalar(
            select(Document.id).where(
                Document.id == payload.entity_id, Document.tenant_id == tenant_id
            )
        )
        return "" if row else None
    if payload.entity_type == "template_version":
        row = await session.scalar(
            select(TemplateVersion.id).where(
                TemplateVersion.id == payload.entity_id, TemplateVersion.tenant_id == tenant_id
            )
        )
        return row
    row = await session.scalar(
        select(DocumentPack.id).where(
            DocumentPack.id == payload.entity_id,
            DocumentPack.tenant_id == tenant_id,
            DocumentPack.deleted_at.is_(None),
        )
    )
    return "" if row else None


async def _validate_binding_context(
    session: AsyncSession, tenant_id: str, context: NpaBindingContext
) -> dict[str, str]:
    """Проверить область действия связи и вернуть её как хранимый словарь.

    Роль — закрытый словарь (тот же, что у требований реестра), площадка —
    живая площадка ЭТОГО арендатора. Выдуманное значение отвергается 422:
    иначе «кого и где касается» снова стало бы свободной строкой, по которой
    ничего не отобрать, — ровно то, из-за чего сводка влияния и показывала
    вечный ноль.
    """

    stored: dict[str, str] = {}
    role_code = (context.role_code or "").strip()
    if role_code:
        if role_code not in ROLE_CODES:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Роли «{role_code}» нет в системе — выберите роль из справочника",
            )
        stored["role_code"] = role_code

    site_id = (context.site_id or "").strip()
    if site_id:
        site = await session.scalar(
            select(Site.id).where(
                Site.id == site_id,
                Site.tenant_id == tenant_id,
                Site.deleted_at.is_(None),
            )
        )
        if site is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Площадка не найдена")
        stored["site_id"] = site_id
    return stored


@router.get("/npa/binding-options")
async def npa_binding_options(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    access=Depends(
        abac(
            _tenant_resource_id,
            required_roles=_IMPACT_WRITE_ROLES,
            action="bind npa act",
        )
    ),
) -> dict[str, list[dict[str, str]]]:
    """Справочники области действия связи (срез-197): роли и площадки.

    Без них «кого и где касается» пришлось бы впечатывать руками — и роль
    снова стала бы свободной строкой, по которой ничего не отобрать. Ровно та
    же причина, по которой у требований реестра появился свой справочник формы
    (срез-147).
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    from app.core.role_labels import role_options
    from app.domains.npa.requirements import RequirementsService

    return {
        "roles": role_options(),
        "sites": await RequirementsService(session, str(tenant.id)).site_options(),
    }


@router.post(
    "/npa/{act_id}/bindings",
    response_model=NpaBindingRead,
    status_code=status.HTTP_201_CREATED,
)
@audit_operation("create", "npa_binding")
async def create_npa_binding(
    act_id: str,
    payload: NpaBindingCreate,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    access=Depends(
        abac(
            _tenant_resource_id,
            required_roles=_IMPACT_WRITE_ROLES,
            action="bind npa act",
        )
    ),
) -> NpaBindingRead:
    """Привязать документ / версию шаблона / пакет арендатора к акту реестра."""
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    act = await get_visible_act(session, act_id, str(tenant.id))
    if act is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "NPA act not found")
    template_version_id = await _binding_target_exists(session, str(tenant.id), payload)
    if template_version_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сущность для привязки не найдена")
    duplicate = await session.scalar(
        select(NPABinding.id).where(
            NPABinding.tenant_id == str(tenant.id),
            NPABinding.npa_id == act_id,
            NPABinding.entity_type == payload.entity_type,
            NPABinding.entity_id == payload.entity_id,
        )
    )
    if duplicate is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Связь с этой сущностью уже есть")
    impact = NpaImpactService(session, str(tenant.id))
    # Новую связь заводят по действующей редакции: сверять её не с чем, кроме
    # текущего текста акта. Без редакций — None, и связь не бывает «не
    # пересмотренной», пока владелец платформы не заведёт первую.
    active = await impact.active_revision_for(act_id)
    # Срез-197: область действия связи («кого и где касается») наконец
    # записывается. До него здесь стояло `context={}`, и категории сводки
    # влияния, читавшие контекст, были вечными нулями.
    context = await _validate_binding_context(session, str(tenant.id), payload.context)
    binding = NPABinding(
        tenant_id=str(tenant.id),
        npa_id=act_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        template_version_id=template_version_id or None,
        ref=payload.ref,
        context=context,
        reviewed_revision_id=active.id if active else None,
    )
    session.add(binding)
    try:
        await session.commit()
    except IntegrityError as exc:
        # Гонка двух одинаковых заявок: уникальный индекс uq_npabinding_target.
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Связь с этой сущностью уже есть") from exc
    await session.refresh(binding)
    return await _binding_read(impact, binding, active)


async def _binding_context_read(session: AsyncSession, binding: NPABinding) -> dict[str, str]:
    """Область действия связи словами: роль подписью, площадка именем.

    Пустой словарь означает «связь касается всего акта», и это отдельное
    состояние — его нельзя путать с «область есть, но мы её не показали».
    """

    stored = binding.context or {}
    out: dict[str, str] = {}
    role_code = str(stored.get("role_code") or "").strip()
    if role_code:
        out["role"] = role_label(role_code) or role_code
    site_id = str(stored.get("site_id") or "").strip()
    if site_id:
        name = await session.scalar(select(Site.name).where(Site.id == site_id))
        # Снесённая площадка: показываем идентификатор, а не пустоту — связь
        # заводили осознанно, и молча её обнулять нельзя.
        out["site"] = name or site_id
    return out


async def _binding_read(
    impact: NpaImpactService, binding: NPABinding, active: NpaRevision | None
) -> NpaBindingRead:
    titles = await impact.binding_titles([binding])
    reviewed_code = None
    if binding.reviewed_revision_id:
        reviewed = await impact.session.get(NpaRevision, binding.reviewed_revision_id)
        reviewed_code = reviewed.revision_code if reviewed else None
    return NpaBindingRead(
        id=binding.id,
        npa_id=binding.npa_id,
        entity_type=str(getattr(binding.entity_type, "value", binding.entity_type)),
        entity_id=binding.entity_id,
        ref=binding.ref,
        # Срез-197: область действия — СЛОВАМИ. Код роли на экране человек
        # читать не должен, а площадка без имени — это просто идентификатор.
        context=await _binding_context_read(impact.session, binding),
        title=titles.get(binding.id, binding.entity_id),
        reviewed_revision_id=binding.reviewed_revision_id,
        reviewed_revision_code=reviewed_code,
        stale=active is not None and binding.reviewed_revision_id != active.id,
    )


@router.post(
    "/npa/{act_id}/bindings/{binding_id}/review",
    response_model=NpaBindingRead,
)
@audit_operation("update", "npa_binding")
async def review_npa_binding(
    act_id: str,
    binding_id: str,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    access=Depends(
        abac(
            _tenant_resource_id,
            required_roles=_IMPACT_WRITE_ROLES,
            action="review npa binding",
        )
    ),
) -> NpaBindingRead:
    """«Пересмотрено»: связь сверена по действующей редакции акта.

    Повторный вызов безвреден — просто ещё раз запишет ту же редакцию.
    """
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    binding = await session.scalar(
        select(NPABinding).where(
            NPABinding.id == binding_id,
            NPABinding.npa_id == act_id,
            NPABinding.tenant_id == str(tenant.id),
        )
    )
    if binding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Связь не найдена")
    impact = NpaImpactService(session, str(tenant.id))
    active = await impact.active_revision_for(act_id)
    binding.reviewed_revision_id = active.id if active else None
    await session.commit()
    await session.refresh(binding)
    return await _binding_read(impact, binding, active)


@router.delete(
    "/npa/{act_id}/bindings/{binding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
@audit_operation("delete", "npa_binding")
async def delete_npa_binding(
    act_id: str,
    binding_id: str,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    access=Depends(
        abac(
            _tenant_resource_id,
            required_roles=_IMPACT_WRITE_ROLES,
            action="unbind npa act",
        )
    ),
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    binding = await session.scalar(
        select(NPABinding).where(
            NPABinding.id == binding_id,
            NPABinding.npa_id == act_id,
            NPABinding.tenant_id == str(tenant.id),
        )
    )
    if binding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Связь не найдена")
    await session.delete(binding)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
