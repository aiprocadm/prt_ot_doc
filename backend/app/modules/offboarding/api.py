"""OPS-72 (разд. 72.2): API полного экспорта данных арендатора.

ТЗ требует **самообслуживания**: «владелец аренды может инициировать экспорт сам,
не через поддержку». Ручка за пределами поддержки — это и есть та кнопка, наличие
которой, по ТЗ, повышает готовность войти: «мы в любой момент заберём данные».

Роли уже: только ``owner`` и ``admin``. Полный дамп содержит все ПДн арендатора
разом — это ровно то действие, которое разд. 63.2 требует держать на коротком
поводке, поэтому линейные роли сюда не допускаются.

Каждый вызов пишется в аудит (разд. 72.2 «Аудит экспорта: кто, когда, какой объём
выгрузил»). Объём фиксируется по манифесту, а не «примерно»: на вопрос «что именно
у нас выгрузили» должен быть точный ответ.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import Tenant
from app.modules.offboarding.export import DEFAULT_ROWS_PER_TABLE, TenantExportService

router = APIRouter(prefix="/offboarding", tags=["offboarding"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

# Полный дамп = все ПДн арендатора разом. Уже, чем чтение отдельных разделов.
_EXPORT_ROLES = ["owner", "admin"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ExportAccess = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id,
            required_roles=_EXPORT_ROLES,
            action="export all tenant data",
        )
    ),
]


@router.get(
    "/export/manifest",
    summary="Состав полного экспорта данных арендатора (без строк)",
)
@audit_operation("offboarding.export_manifest", "tenant")
async def export_manifest(
    tenant: TenantDep,
    session: SessionDep,
    access: ExportAccess,
) -> dict:
    """Что именно будет выгружено: таблицы, число строк, признак усечения.

    Отдельная лёгкая ручка нужна, чтобы владелец увидел объём ДО того, как
    запросит сам дамп: «полный экспорт» на многогигабайтном арендаторе — не то,
    что стоит запускать вслепую.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access

    service = TenantExportService(
        session, tenant_id=str(tenant.id), tenant_slug=tenant.slug
    )
    manifest = await service.build(include_rows=False)
    return manifest.to_dict(include_rows=False)


@router.get(
    "/export",
    summary="Полный экспорт данных арендатора (152-ФЗ, право забрать свои данные)",
)
@audit_operation("offboarding.export", "tenant")
async def export_tenant_data(
    tenant: TenantDep,
    session: SessionDep,
    access: ExportAccess,
    rows_per_table: Annotated[
        int,
        Query(ge=1, le=DEFAULT_ROWS_PER_TABLE, description="Потолок строк на таблицу"),
    ] = DEFAULT_ROWS_PER_TABLE,
) -> dict:
    """Машиночитаемый дамп со схемой, пригодный для переноса в другую систему."""

    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access

    service = TenantExportService(
        session,
        tenant_id=str(tenant.id),
        tenant_slug=tenant.slug,
        rows_per_table=rows_per_table,
    )
    manifest = await service.build(include_rows=True)
    return manifest.to_dict(include_rows=True)
