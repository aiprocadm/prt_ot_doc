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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import Tenant
from app.modules.offboarding.export import DEFAULT_ROWS_PER_TABLE, TenantExportService
from app.modules.offboarding.lifecycle import DEFAULT_GRACE_DAYS, TenantOffboardingService


class OffboardingRequest(BaseModel):
    reason: str | None = None
    grace_days: int = Field(default=DEFAULT_GRACE_DAYS, ge=0, le=365)


class OffboardingCancel(BaseModel):
    reason: str | None = None


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


def _serialize_offboarding(record) -> dict:  # noqa: ANN001 - ORM row
    return {
        "id": str(record.id),
        "status": record.status,
        "reason": record.reason,
        "requested_at": record.requested_at.isoformat(),
        "grace_days": record.grace_days,
        "grace_until": record.grace_until.isoformat(),
        "cancelled_at": record.cancelled_at.isoformat() if record.cancelled_at else None,
        "purged_at": record.purged_at.isoformat() if record.purged_at else None,
        "purge_act": record.purge_act,
        "requested_by_email": record.requested_by_email,
    }


@router.get("/status", summary="Статус офбординга арендатора (152-ФЗ, разд. 72.3)")
async def offboarding_status(
    tenant: TenantDep,
    session: SessionDep,
    access: ExportAccess,
) -> dict:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access

    record = await TenantOffboardingService(
        session, tenant_id=str(tenant.id), tenant_slug=tenant.slug
    ).current()
    return {"offboarding": _serialize_offboarding(record) if record else None}


@router.post(
    "/request",
    status_code=status.HTTP_201_CREATED,
    summary="Подать заявку на расторжение (стартует grace-период)",
)
@audit_operation("offboarding.request", "tenant")
async def request_offboarding(
    payload: OffboardingRequest,
    tenant: TenantDep,
    session: SessionDep,
    access: ExportAccess,
) -> dict:
    """Заявка стартует grace-период: данные ещё живут N дней на случай возврата."""

    TenantContextValidator.ensure_tenant_context(tenant)

    service = TenantOffboardingService(
        session, tenant_id=str(tenant.id), tenant_slug=tenant.slug
    )
    record = await service.request(
        reason=payload.reason,
        grace_days=payload.grace_days,
        actor_user_id=str(access.user.id) if access.user else None,
        actor_email=getattr(access.user, "email", None),
    )
    return _serialize_offboarding(record)


@router.post("/cancel", summary="Отменить расторжение (клиент вернулся)")
@audit_operation("offboarding.cancel", "tenant")
async def cancel_offboarding(
    payload: OffboardingCancel,
    tenant: TenantDep,
    session: SessionDep,
    access: ExportAccess,
) -> dict:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access

    service = TenantOffboardingService(
        session, tenant_id=str(tenant.id), tenant_slug=tenant.slug
    )
    record = await service.cancel(reason=payload.reason)
    if record is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="OFFBOARDING_NOT_ACTIVE",
                message="No active offboarding request to cancel",
                error_type="offboarding",
            ),
        )
    return _serialize_offboarding(record)


@router.get(
    "/purge-plan",
    summary="План удаления: что удалим, что сохраним обезличенным и почему",
)
@audit_operation("offboarding.purge_plan", "tenant")
async def purge_plan(
    tenant: TenantDep,
    session: SessionDep,
    access: ExportAccess,
) -> dict:
    """Юридические исключения берутся из реестра обработки (SEC-66 срез-3):
    у процесса указан срок хранения ВМЕСТЕ со ссылкой на норму, поэтому «почему
    это нельзя удалить» — не мнение, а данные."""

    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access

    service = TenantOffboardingService(
        session, tenant_id=str(tenant.id), tenant_slug=tenant.slug
    )
    return (await service.build_purge_plan()).to_dict()
