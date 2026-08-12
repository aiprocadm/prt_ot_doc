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
from app.db.session import AsyncSessionLocal
from app.domains.reseller.legal import (
    LEGAL_KIND_TITLES,
    LegalDocument,
    LegalDocumentKind,
    resolve_legal_document,
)
from app.models.legal_documents import TenantLegalDocument
from app.models.models import Tenant
from app.schemas.legal_documents import (
    LegalDocumentList,
    LegalDocumentPublish,
    LegalDocumentRead,
    LegalDocumentSummary,
)

public_router = APIRouter(prefix="/public/legal", tags=["legal"])
router = APIRouter(prefix="/platform/legal", tags=["legal"])
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
            await _current_row(session, str(tenant.parent_id), kind)
            if tenant.parent_id
            else None
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


def _require_legal_editor(
    credentials: HTTPAuthorizationCredentials | None, tenant: Tenant
) -> None:
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
