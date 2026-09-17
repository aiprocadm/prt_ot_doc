"""Журнал доступа в кабинете САМОГО клиента (SEC-63 остаток, Доп. №3 разд. 63.2).

Срез-2 SEC-63 дал журнал «кто из специалистов работал в данных клиента» — но в
кабинете АУТСОРСЕРА, с пометкой «показать его клиенту — обязанность аутсорсера
по договору». Для клиента в режиме Dedicated это половина ответа: у него есть
свой арендатор и свой вход, а следы работы аутсорсера лежат в чужом контуре, и
увидеть их он может только попросив того, за кем и следит.

**Записи не дублируются, а читаются.** Зеркалировать аудит в арендатора клиента
нельзя: цепочка записей подписана и проверяется на несмываемость (SEC-63
срез-2), и вставка в неё чужих строк сломала бы проверку целостности у клиента.
Одна правда, прочитанная доверенной сессией, честнее двух копий.

Модуль `managed_clients` здесь НЕ требуется: он про кабинет аутсорсера, а у
клиента его нет и быть не должно. Право знать, кто трогал твои данные, не должно
зависеть от чужой подписки.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.dependencies import get_tenant_record
from app.api.routes.managed_clients import access_log_entry
from app.core.security import AccessContext, abac
from app.db.session import AsyncSessionLocal
from app.domains.managed_clients.served_by import ClientAccessView, ServingOutsourcer
from app.models.audit_log import AuditLog
from app.models.managed_clients import ManagedClient
from app.models.models import Tenant
from app.schemas.managed_clients import MyAccessLogPage

router = APIRouter(prefix="/my-access-log", tags=["managed-clients"])


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


#: Журнал доступа к данным организации — вопрос ответственного лица, а не любого
#: сотрудника: в нём видно, кто из подрядчиков и когда заходил.
_ROLES = ["owner", "admin"]
Access = Annotated[AccessContext, Depends(abac(_tenant_resource_id, required_roles=_ROLES))]


def _trusted_session():
    """Доверенная сессия: записи лежат в арендаторе аутсорсера.

    Под FORCE RLS (SEC-65) сессия клиента их не увидит — они принадлежат другому
    арендатору. Это не дыра: наружу уходят ТОЛЬКО записи о работе в данных
    этого самого клиента, то есть то, что разд. 63.2 обязывает ему показать.
    """

    return AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    )


async def _resolve_outsourcer(tenant_slug: str) -> ServingOutsourcer | None:
    """Найти аутсорсера по слагу арендатора клиента.

    Связь идёт через `dedicated_tenant_slug`, а НЕ через родителя: родителем
    нового арендатора становится контур, где нажали кнопку перевода, и если сам
    аутсорсер — клиент реселлера, родителем окажется реселлер. По родителю мы
    нашли бы не того, кто работает в данных.
    """

    async with _trusted_session() as session:
        row = (
            await session.execute(
                select(ManagedClient.id, ManagedClient.tenant_id, Tenant.name)
                .join(Tenant, Tenant.id == ManagedClient.tenant_id)
                .where(
                    ManagedClient.dedicated_tenant_slug == tenant_slug,
                    ManagedClient.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).first()
    if row is None:
        return None
    return ServingOutsourcer(managed_client_id=row[0], tenant_id=row[1], tenant_name=row[2])


@router.get("", response_model=MyAccessLogPage)
async def read_my_access_log(
    tenant: Tenant = Depends(get_tenant_record),
    _access: Access = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MyAccessLogPage:
    """Кто из обслуживающей компании работал в моих данных.

    Разд. 63.2: «клиент может запросить журнал доступа к своим данным». Раньше
    запросить его можно было только У АУТСОРСЕРА — то есть у того, за кем
    следят. Здесь тот же журнал открыт в кабинете клиента.

    Пустой список — обычный ответ, а не ошибка: арендатора могут не обслуживать
    вовсе. Поэтому рядом идёт объяснение словами.
    """

    outsourcer = await _resolve_outsourcer(tenant.slug)
    view = ClientAccessView(served_by=outsourcer)
    if outsourcer is None:
        return MyAccessLogPage(items=[], total=0, served_by=None, summary=view.summary)

    conditions = [
        AuditLog.tenant_id == outsourcer.tenant_id,
        AuditLog.object_type == "managed_client",
        # Только записи ПРО ЭТОГО клиента: у аутсорсера их много, и чужие
        # обращения его подопечных клиенту видеть нельзя.
        AuditLog.object_id == outsourcer.managed_client_id,
        AuditLog.action == "managed_client.context.enter",
    ]
    if since is not None:
        conditions.append(AuditLog.when >= since)
    if until is not None:
        conditions.append(AuditLog.when <= until)

    async with _trusted_session() as session:
        total = int(
            (
                await session.execute(select(func.count()).select_from(AuditLog).where(*conditions))
            ).scalar_one_or_none()
            or 0
        )
        rows = (
            (
                await session.execute(
                    select(AuditLog)
                    .where(*conditions)
                    .order_by(AuditLog.when.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )

    return MyAccessLogPage(
        items=[access_log_entry(row) for row in rows],
        total=total,
        served_by=outsourcer.tenant_name,
        summary=view.summary,
    )
