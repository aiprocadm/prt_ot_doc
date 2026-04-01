from __future__ import annotations

from collections.abc import Iterable

from fastapi import APIRouter, Depends

from app.api.dependencies import require_tenant_slug
from app.api.routes import (
    admin_authz,
    admin_users,
    api_tokens,
    approval_orchestration,
    approval_signing_v1,
    attestations,
    audit,
    auth,
    billing,
    briefings,
    calendar,
    client_portal,
    companies,
    compliance,
    contracts,
    dashboard,
    departments,
    documents,
    edo_workflow,
    external_registry,
    incidents,
    inspections,
    integration_readiness,
    invoices,
    jobs,
    journals,
    medical,
    notifications,
    npa,
    obligations,
    orders,
    outbox_admin,
    packs,
    persons,
    ppe,
    prescriptions,
    public_api,
    pwa_sync,
    reports,
    risk,
    risk_enterprise,
    safety_ops,
    sites,
    tasks,
    tenancy,
    tenants,
    training,
    training_next,
    webhooks,
    workspace,
)
from app.modules.analytics.api import router as analytics_router
from app.modules.branding.api import router as branding_router
from app.modules.client_portal.api import internal_router as portal_requests_router
from app.modules.client_portal.api import router as client_portal_v1_router
from app.modules.export_center.api import router as export_center_router
from app.modules.files.api import router as files_v1_router
from app.modules.headers import api as headers_api
from app.modules.packs import api as packs_v2_api
from app.modules.pdf import api as pdf_api
from app.modules.pipelines import api as pipelines_api
from app.modules.replace import api as replace_api
from app.modules.search.api import router as search_router
from app.modules.workflow.api import router as workflow_router

RouterRegistration = tuple[APIRouter, dict[str, object]]
ROUTER_GROUP_ORDER = (
    "public",
    "compliance_and_admin",
    "operations",
    "document_core",
    "platform_extension",
)


PUBLIC_ROUTER_REGISTRATIONS: tuple[RouterRegistration, ...] = (
    (auth.router, {"prefix": "/auth", "tags": ["auth"]}),
    (client_portal.router, {}),
)

COMPLIANCE_AND_ADMIN_ROUTER_REGISTRATIONS: tuple[RouterRegistration, ...] = (
    (audit.router, {"prefix": "/audit", "tags": ["audit"]}),
    (admin_users.router, {"tags": ["admin-users"]}),
    (admin_authz.router, {}),
    (attestations.router, {"tags": ["attestations"]}),
    (notifications.router, {}),
    (departments.router, {"tags": ["departments"]}),
    (contracts.router, {"tags": ["contracts"]}),
    (dashboard.router, {"tags": ["dashboard"]}),
    (orders.router, {"tags": ["orders"]}),
    (invoices.router, {"tags": ["invoices"]}),
    (npa.router, {"tags": ["npa"]}),
    (ppe.router, {"tags": ["ppe"]}),
    (medical.router, {"tags": ["medical"]}),
    (journals.router, {"tags": ["journals"]}),
    (risk.router, {"tags": ["risks"]}),
    (risk_enterprise.router, {}),
    (sites.router, {"tags": ["sites"]}),
    (companies.router, {}),
    (persons.router, {}),
    (training.router, {"tags": ["training"]}),
    (training_next.router, {}),
    (briefings.router, {}),
    (calendar.router, {}),
    (compliance.router, {}),
    (billing.router, {}),
)

OPERATIONS_ROUTER_REGISTRATIONS: tuple[RouterRegistration, ...] = (
    (files_v1_router, {"prefix": "/files", "tags": ["files"]}),
    (packs.router, {"prefix": "/packs", "tags": ["packs"]}),
    (client_portal.presets_router, {}),
    (client_portal.internal_router, {}),
    (incidents.router, {"tags": ["incidents"]}),
    (inspections.router, {"tags": ["inspections"]}),
    (prescriptions.router, {"tags": ["prescriptions"]}),
    (safety_ops.router, {"tags": ["safety-ops"]}),
    (obligations.router, {"tags": ["obligations"]}),
    (jobs.router, {}),
    (tasks.router, {"prefix": "/tasks", "tags": ["tasks"]}),
    (workspace.router, {}),
    (tenancy.router, {}),
    (outbox_admin.router, {"prefix": "/admin/outbox", "tags": ["outbox"]}),
    (webhooks.router, {}),
    (integration_readiness.router, {}),
    (tenants.router, {}),
    (tenants.admin_router, {}),
    (pwa_sync.router, {}),
    (external_registry.router, {}),
    (reports.router, {"tags": ["reports"]}),
)

DOCUMENT_CORE_ROUTER_REGISTRATIONS: tuple[RouterRegistration, ...] = (
    (documents.router, {"prefix": "/documents", "tags": ["documents"]}),
    (edo_workflow.router, {"tags": ["edo-workflow"]}),
    (approval_signing_v1.router, {"prefix": "/v1", "tags": ["approval-signing-v1"]}),
    (approval_orchestration.router, {"tags": ["approval-orchestration"]}),
    (replace_api.router, {}),
    (headers_api.router, {"tags": ["layout-presets"]}),
    (branding_router, {}),
    (pipelines_api.router, {}),
    (workflow_router, {}),
    (pdf_api.router, {"prefix": "/files", "tags": ["pdf"]}),
    (packs_v2_api.router, {}),
    (search_router, {"tags": ["search"]}),
    (analytics_router, {"tags": ["analytics"]}),
    (export_center_router, {"tags": ["exports"]}),
)

PLATFORM_EXTENSION_ROUTER_REGISTRATIONS: tuple[RouterRegistration, ...] = (
    (client_portal_v1_router, {}),
    (public_api.admin_router, {}),
    (public_api.marketplace_router, {}),
    (public_api.router, {}),
    (api_tokens.router, {}),
    (portal_requests_router, {}),
)

ROUTER_GROUPS: dict[str, tuple[RouterRegistration, ...]] = {
    "public": PUBLIC_ROUTER_REGISTRATIONS,
    "compliance_and_admin": COMPLIANCE_AND_ADMIN_ROUTER_REGISTRATIONS,
    "operations": OPERATIONS_ROUTER_REGISTRATIONS,
    "document_core": DOCUMENT_CORE_ROUTER_REGISTRATIONS,
    "platform_extension": PLATFORM_EXTENSION_ROUTER_REGISTRATIONS,
}


def create_public_router() -> APIRouter:
    router = APIRouter()
    _include_registrations(router, ROUTER_GROUPS["public"])
    return router


def create_tenant_router() -> APIRouter:
    router = APIRouter(dependencies=[Depends(require_tenant_slug)])
    for group_name in ROUTER_GROUP_ORDER[1:]:
        _include_registrations(router, ROUTER_GROUPS[group_name])
    return router


def _include_registrations(router: APIRouter, registrations: Iterable[RouterRegistration]) -> None:
    for child, kwargs in registrations:
        router.include_router(child, **kwargs)


def describe_router_groups() -> dict[str, list[dict[str, object]]]:
    description: dict[str, list[dict[str, object]]] = {}
    for group_name in ROUTER_GROUP_ORDER:
        description[group_name] = [
            {
                "prefix": kwargs.get("prefix", ""),
                "tags": list(kwargs.get("tags", [])),
                "routes": len(child.routes),
            }
            for child, kwargs in ROUTER_GROUPS[group_name]
        ]
    return description
