"""Юридические тексты: чтение всеми, публикация — владельцем платформы и партнёром.

Доп. №1 разд. 52.2, четвёртый пункт. Ручки:

* ``GET /public/legal`` — какие тексты действуют у этого арендатора (без тела).
* ``GET /public/legal/{kind}`` — сам текст. Обе БЕЗ токена: оферту и политику
  ПДн человек обязан прочитать ДО входа, иначе ссылка на них бессмысленна.
* ``GET /platform/legal/{kind}`` — своя действующая редакция.
* ``PUT /platform/legal/{kind}`` — опубликовать новую редакцию.

Публикует только владелец платформы или партнёр — та же область флота, что в
срезе-2: кто продаёт платформу, тот и отвечает за её юридические тексты.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.security import AccessContext, rbac
from app.db.session import AsyncSessionLocal
from app.domains.reseller.legal import (
    LEGAL_KIND_TITLES,
    LegalDocument,
    LegalDocumentKind,
    resolve_legal_document,
)
from app.domains.reseller.legal_acceptance import (
    AcceptanceState,
    document_fingerprint,
    pending_kinds,
)
from app.models.legal_acceptance import TenantLegalAcceptance
from app.models.legal_documents import TenantLegalDocument
from app.models.models import Tenant
from app.schemas.legal_documents import (
    LegalAcceptanceRead,
    LegalAcceptanceState,
    LegalAcceptanceStatus,
    LegalDocumentList,
    LegalDocumentPublish,
    LegalDocumentRead,
    LegalDocumentSummary,
)

public_router = APIRouter(prefix="/public/legal", tags=["legal"])
router = APIRouter(prefix="/platform/legal", tags=["legal"])
#: Принятие живёт отдельным префиксом: это НЕ публичное чтение (нужен человек)
#: и НЕ управление текстами (принимает любой сотрудник, а публикует только
#: партнёр). Смешать с `/platform/legal` значило бы завести одну дверь с двумя
#: разными правилами доступа.
acceptance_router = APIRouter(prefix="/legal/acceptance", tags=["legal"])
_optional_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _legal_session() -> AsyncSession:
    """Доверенная сессия общей схемы.

    ``rls_bypass``: клиенту нужен текст ЕГО ПАРТНЁРА — строка другого
    арендатора, под FORCE RLS (SEC-65) невидимая. Это не дыра: публичная оферта
    на то и публичная, наружу уходит только опубликованный текст.
    """

    return AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    )


async def _current_row(
    session: AsyncSession, tenant_id: str, kind: LegalDocumentKind
) -> TenantLegalDocument | None:
    """Действующая редакция — с наибольшим номером.

    Сортировка по номеру, а не по дате: две публикации в одну секунду дали бы
    одинаковое время, и «действующей» оказалась бы произвольная из них.
    """

    return (
        (
            await session.execute(
                select(TenantLegalDocument)
                .where(
                    TenantLegalDocument.tenant_id == tenant_id,
                    TenantLegalDocument.kind == kind.value,
                )
                .order_by(TenantLegalDocument.doc_version.desc())
            )
        )
        .scalars()
        .first()
    )


def _as_document(row: TenantLegalDocument, source: str) -> LegalDocument:
    return LegalDocument(
        kind=LegalDocumentKind(row.kind),
        title=row.title,
        body=row.body,
        version=row.doc_version,
        source=source,
    )


async def _effective(
    tenant: Tenant, kind: LegalDocumentKind
) -> tuple[LegalDocument, datetime] | None:
    async with _legal_session() as session:
        own_row = await _current_row(session, tenant.id, kind)
        parent_row = (
            await _current_row(session, str(tenant.parent_id), kind) if tenant.parent_id else None
        )
        document = resolve_legal_document(
            kind,
            own=_as_document(own_row, "self") if own_row else None,
            reseller=_as_document(parent_row, "reseller") if parent_row else None,
        )
        if document is None:
            return None
        # Дата берётся у ТОЙ ЖЕ строки, что дала текст: показать редакцию
        # партнёра с датой публикации клиента значило бы соврать о документе.
        # Без `assert`: с ключом `-O` он выключается, и вместо понятной ошибки
        # получился бы `AttributeError` на `None` в бою.
        chosen = own_row if document.source == "self" else parent_row
        if chosen is None:  # pragma: no cover - недостижимо: ступень выбрана по строке
            return None
        return document, chosen.published_at


@public_router.get("", response_model=LegalDocumentList)
async def list_public_legal(
    tenant: Tenant = Depends(get_tenant_record),
) -> LegalDocumentList:
    """Какие тексты действуют — без тел, чтобы список был дешёвым."""

    items: list[LegalDocumentSummary] = []
    for kind in LegalDocumentKind:
        found = await _effective(tenant, kind)
        if found is None:
            continue
        document, published_at = found
        items.append(
            LegalDocumentSummary(
                kind=document.kind,
                title=document.title,
                version=document.version,
                source=document.source,
                published_at=published_at,
            )
        )
    return LegalDocumentList(items=items)


@public_router.get("/{kind}", response_model=LegalDocumentRead)
async def read_public_legal(
    kind: LegalDocumentKind,
    tenant: Tenant = Depends(get_tenant_record),
) -> LegalDocumentRead:
    found = await _effective(tenant, kind)
    if found is None:
        # Именно 404: «текста нет» — это отсутствие документа, а не отказ в
        # доступе. Пустой текст с кодом 200 читался бы как «оферта пустая».
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не опубликован")
    document, published_at = found
    return LegalDocumentRead(
        kind=document.kind,
        title=document.title,
        body=document.body,
        version=document.version,
        source=document.source,
        published_at=published_at,
    )


def _require_legal_editor(credentials: HTTPAuthorizationCredentials | None, tenant: Tenant) -> None:
    """Публиковать тексты может владелец платформы или партнёр.

    Переиспользует область флота (срез-2): кто продаёт платформу, тот и
    отвечает за её юридические тексты. Своё правило здесь разъехалось бы с
    остальными при первом изменении уровней.
    """

    from app.api.routes.platform_tenants import _require_fleet_actor

    _require_fleet_actor(credentials, tenant)


@router.get("/{kind}", response_model=LegalDocumentRead)
async def read_own_legal(
    kind: LegalDocumentKind,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> LegalDocumentRead:
    _require_legal_editor(credentials, tenant)
    row = await _current_row(session, tenant.id, kind)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Своя редакция не опубликована")
    return LegalDocumentRead(
        kind=LegalDocumentKind(row.kind),
        title=row.title,
        body=row.body,
        version=row.doc_version,
        source="self",
        published_at=row.published_at,
    )


@router.put("/{kind}", response_model=LegalDocumentRead, status_code=status.HTTP_201_CREATED)
@audit_operation("publish", "tenant_legal_document")
async def publish_legal(
    kind: LegalDocumentKind,
    payload: LegalDocumentPublish,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> LegalDocumentRead:
    """Опубликовать новую редакцию.

    Прежняя НЕ правится и не удаляется: вопрос «какая редакция действовала в
    марте» юридический, и ответить на него можно только по неизменной истории.
    """

    _require_legal_editor(credentials, tenant)
    previous = await _current_row(session, tenant.id, kind)
    published_at = datetime.now(timezone.utc)
    row = TenantLegalDocument(
        tenant_id=tenant.id,
        kind=kind.value,
        title=payload.title.strip() or LEGAL_KIND_TITLES[kind],
        body=payload.body,
        doc_version=(previous.doc_version + 1) if previous else 1,
        published_at=published_at,
    )
    session.add(row)
    await session.commit()

    return LegalDocumentRead(
        kind=kind,
        title=row.title,
        body=row.body,
        version=row.doc_version,
        source="self",
        published_at=published_at,
    )


# --- принятие текстов (BIZ-52 срез-11) ----------------------------------------


async def _acceptance_rows(
    session: AsyncSession, tenant_id: str, user_id: str
) -> dict[str, TenantLegalAcceptance]:
    """Последнее принятие каждого вида этим человеком.

    Своя строка — читается обычной сессией: принятие принадлежит арендатору
    пользователя, обходить RLS здесь не за чем.
    """

    rows = (
        (
            await session.execute(
                select(TenantLegalAcceptance)
                .where(
                    TenantLegalAcceptance.tenant_id == tenant_id,
                    TenantLegalAcceptance.user_id == user_id,
                )
                .order_by(TenantLegalAcceptance.doc_version.desc())
            )
        )
        .scalars()
        .all()
    )
    latest: dict[str, TenantLegalAcceptance] = {}
    for row in rows:
        latest.setdefault(row.kind, row)
    return latest


@acceptance_router.get("", response_model=LegalAcceptanceState)
async def read_acceptance_state(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    ctx: AccessContext = Depends(rbac()),
) -> LegalAcceptanceState:
    """Что действует и что этот человек уже принял.

    Доступна ЛЮБОМУ пользователю арендатора: подписывает каждый за себя, и
    закрытие ручки ролью оставило бы рядового сотрудника без возможности узнать,
    что от него ждут подписи (грабля BIZ-61 среза-5 — там ровно так и вышло).
    """

    accepted = await _acceptance_rows(session, tenant.id, str(ctx.user.id))
    items: list[LegalAcceptanceStatus] = []
    states: list[AcceptanceState] = []
    for kind in LegalDocumentKind:
        effective = await _effective(tenant, kind)
        row = accepted.get(kind.value)
        current_version = effective[0].version if effective else None
        state = AcceptanceState(
            kind=kind.value,
            current_version=current_version,
            accepted_version=row.doc_version if row else None,
        )
        states.append(state)
        items.append(
            LegalAcceptanceStatus(
                kind=kind,
                title=effective[0].title if effective else None,
                current_version=current_version,
                accepted_version=row.doc_version if row else None,
                accepted_at=row.accepted_at if row else None,
                accepted=state.accepted,
                outdated=state.outdated,
            )
        )
    return LegalAcceptanceState(
        items=items,
        pending=[LegalDocumentKind(kind) for kind in pending_kinds(states)],
    )


@acceptance_router.post(
    "/{kind}", response_model=LegalAcceptanceRead, status_code=status.HTTP_201_CREATED
)
@audit_operation("accept", "tenant_legal_acceptance")
async def accept_legal(
    kind: LegalDocumentKind,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    ctx: AccessContext = Depends(rbac()),
) -> LegalAcceptanceRead:
    """Зафиксировать принятие ДЕЙСТВУЮЩЕЙ редакции.

    Номер редакции и текст НЕ принимаются от клиента: сервер берёт ровно то, что
    сам же и показывает. Прими их снаружи — и запись «принята редакция 3»
    перестала бы значить, что человек видел именно её.

    Повторное принятие той же редакции возвращает прежнюю запись, а не ошибку:
    двойное нажатие кнопки — обычное дело, а 409 выглядел бы как поломка. Время
    при этом сохраняется ПЕРВОЕ: «когда согласился» — это когда согласился
    впервые.
    """

    effective = await _effective(tenant, kind)
    if effective is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Текст не опубликован")
    document, _published_at = effective

    existing = (
        await session.execute(
            select(TenantLegalAcceptance).where(
                TenantLegalAcceptance.tenant_id == tenant.id,
                TenantLegalAcceptance.user_id == str(ctx.user.id),
                TenantLegalAcceptance.kind == kind.value,
                TenantLegalAcceptance.doc_version == document.version,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return LegalAcceptanceRead(
            kind=kind,
            doc_version=existing.doc_version,
            source=existing.source,
            accepted_at=existing.accepted_at,
        )

    row = TenantLegalAcceptance(
        tenant_id=tenant.id,
        user_id=str(ctx.user.id),
        kind=kind.value,
        doc_version=document.version,
        source=document.source,
        body_sha256=document_fingerprint(document.body),
        accepted_at=datetime.now(timezone.utc),
    )
    session.add(row)
    await session.commit()

    return LegalAcceptanceRead(
        kind=kind,
        doc_version=row.doc_version,
        source=row.source,
        accepted_at=row.accepted_at,
    )
