"""BIZ-49 срез-7 (разд. 49.3): зависимость «работа в контексте клиента».

Любой роут, который должен уметь работать ОТ ИМЕНИ ведомого клиента, объявляет
``ClientContextDep``. Зависимость:

1. читает заголовок ``X-Managed-Client`` (аналог ``X-Tenant``, но внутри портфеля);
2. проверяет действующий грант из матрицы доступа (срез-6);
3. **пишет обязательную пометку в аудит** — кто, от имени какого клиента, что
   сделал. Это прямое требование ТЗ по ПДн, поэтому запись НЕ «best-effort»:
   не удалось записать след — действие не выполняется.

Заголовок отсутствует → контекста нет (``None``), роут работает как обычно.
Заголовок есть, а гранта нет → **403**, а не тихое игнорирование: специалист
должен узнать, что он НЕ в контексте клиента, до того как что-то напишет.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.errors import api_problem_detail
from app.core.security import AuthContext, get_auth_ctx
from app.domains.managed_clients.access import AccessGrant
from app.domains.managed_clients.context import (
    ClientContext,
    ClientContextDenied,
    build_context_audit_meta,
    resolve_client_context,
)
from app.models.managed_clients import ManagedClient, ManagedClientAccess
from app.models.tenanting import Tenant
from app.modules.audit.writer import write_audit_event

__all__ = ["CLIENT_CONTEXT_HEADER", "ClientContextDep", "require_client_context"]

CLIENT_CONTEXT_HEADER = "X-Managed-Client"


def _denied(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=api_problem_detail(
            code="MANAGED_CLIENT_CONTEXT_DENIED",
            message=message,
            error_type="managed_clients",
        ),
    )


async def require_client_context(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    tenant: Annotated[Tenant, Depends(get_tenant_record)],
    auth: Annotated[AuthContext, Depends(get_auth_ctx)],
    x_managed_client: Annotated[str | None, Header(alias=CLIENT_CONTEXT_HEADER)] = None,
) -> ClientContext | None:
    """Подтвердить контекст клиента, если он заявлен, и записать след."""

    if not x_managed_client:
        return None

    now = datetime.now(tz=timezone.utc)
    client = (
        await session.execute(
            select(ManagedClient).where(
                ManagedClient.id == x_managed_client,
                ManagedClient.tenant_id == tenant.id,
                ManagedClient.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if client is None:
        # Тот же ответ, что и при отсутствии гранта: существование чужого
        # клиента — тоже сведения, которых спрашивающий знать не должен.
        raise _denied("Нет доступа к этому клиенту")

    row = (
        await session.execute(
            select(ManagedClientAccess).where(
                ManagedClientAccess.tenant_id == tenant.id,
                ManagedClientAccess.managed_client_id == client.id,
                ManagedClientAccess.user_id == auth.sub,
                ManagedClientAccess.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    grant = (
        AccessGrant(
            client_id=row.managed_client_id,
            user_id=row.user_id,
            all_modules=bool(row.all_modules),
            modules=tuple(row.modules or ()),
            revoked_at=row.revoked_at,
        )
        if row is not None
        else None
    )

    try:
        context = resolve_client_context(
            grant=grant,
            user_id=auth.sub,
            client_id=client.id,
            client_name=client.name,
            now=now,
        )
    except ClientContextDenied as exc:
        raise _denied(str(exc)) from exc

    # Обязательная пометка: ТЗ требует трассируемости действий аутсорсера
    # в данных клиента. Ошибку записи НЕ глушим — без следа работать нельзя.
    await write_audit_event(
        session=session,
        request=request,
        tenant_id=str(tenant.id),
        actor_id=auth.sub,
        action="managed_client.context.enter",
        resource_type="managed_client",
        resource_id=client.id,
        before=None,
        after=None,
        meta=build_context_audit_meta(context, action=str(request.url.path)),
    )
    request.state.managed_client_context = context
    return context


ClientContextDep = Annotated[ClientContext | None, Depends(require_client_context)]
