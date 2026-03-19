from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, rbac
from app.models.models import Tenant, TenantIntegrationKey, WebhookDelivery, WebhookEndpoint
from app.services.integrations.factory import (
    get_accounting_integration,
    get_edo_integration,
    get_eisot_integration,
    get_frdo_integration,
)
from app.services.integrations.interfaces import IntegrationDisabledError

router = APIRouter(prefix="/integrations/readiness", tags=["integration-readiness"])


async def _provider_health(provider_name: str) -> dict[str, Any]:
    providers = {
        "1c": get_accounting_integration,
        "edo": get_edo_integration,
        "frdo": get_frdo_integration,
        "eisot": get_eisot_integration,
    }
    factory = providers.get(provider_name)
    if factory is None:
        return {"provider": provider_name, "health_status": "contract_only", "reachable": None}
    integration = factory()
    try:
        reachable = await integration.health_check()
        return {
            "provider": provider_name,
            "adapter": integration.name,
            "health_status": "ready" if reachable else "degraded",
            "reachable": bool(reachable),
        }
    except IntegrationDisabledError as exc:
        return {
            "provider": provider_name,
            "adapter": integration.name,
            "health_status": "disabled",
            "reachable": False,
            "message": str(exc),
        }


@router.get("")
async def get_integration_readiness(
    _: AccessContext = Depends(rbac(["admin", "owner", "integrations"])),
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
):
    configured_rows = (
        await session.execute(
            select(TenantIntegrationKey).where(TenantIntegrationKey.tenant_id == tenant.id)
        )
    ).scalars().all()
    configured_by_provider = {row.provider: row for row in configured_rows}

    webhook_summary = (
        await session.execute(
            select(
                func.count(WebhookEndpoint.id),
                func.sum(case((WebhookEndpoint.is_enabled.is_(True), 1), else_=0)),
            ).where(WebhookEndpoint.tenant_id == tenant.id)
        )
    ).one()
    delivery_summary = (
        await session.execute(
            select(
                func.count(WebhookDelivery.id),
                func.sum(case((WebhookDelivery.status == "sent", 1), else_=0)),
                func.sum(case((WebhookDelivery.status.in_(["failed", "dead"]), 1), else_=0)),
            ).where(WebhookDelivery.tenant_id == tenant.id)
        )
    ).one()

    providers: list[dict[str, Any]] = []
    for provider_name in ["1c", "edo", "frdo", "eisot", "epgu", "oidc", "ldap"]:
        meta = configured_by_provider.get(provider_name)
        info = await _provider_health(provider_name)
        info["configured"] = meta is not None
        info["config_meta"] = meta.meta_json if meta is not None else {}
        if provider_name in {"epgu", "oidc", "ldap"}:
            info.setdefault("health_status", "contract_only")
            info.setdefault("reachable", None)
            info["contract"] = {
                "auth_mode": "machine-to-machine" if provider_name == "epgu" else "federated-login",
                "supports_diagnostics": True,
                "supports_delivery_journal": provider_name == "epgu",
            }
        providers.append(info)

    return {
        "tenant_id": str(tenant.id),
        "providers": providers,
        "webhooks": {
            "configured_total": int(webhook_summary[0] or 0),
            "enabled_total": int(webhook_summary[1] or 0),
            "delivery_total": int(delivery_summary[0] or 0),
            "delivery_sent_total": int(delivery_summary[1] or 0),
            "delivery_failed_total": int(delivery_summary[2] or 0),
        },
        "notes": [
            "EPGU/OIDC/LDAP exposed as readiness contracts and diagnostics placeholders for future certified adapters.",
            "1C/EDO/FRDO/EISOT use provider factories and return live health when adapters are enabled.",
        ],
    }
