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
    branches,
    briefings,
    calendar,
    calendar_views,
    client_portal,
    committees,
    companies,
    compliance,
    contractors,
    contracts,
    dashboard,
    data_quality,
    departments,
    documents,
    edo_workflow,
    employees,
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
    operational_dashboard,
    orders,
    outbox_admin,
    packs,
    pep_signing,
    permits,
    persons,
    platform_tenants,
    ppe,
    prescriptions,
    public_api,
    pwa_sync,
    reports,
    risk,
    risk_enterprise,
    safety_ops,
    sites,
    sout,
    tasks,
    tenancy,
    tenants,
    training,
    training_next,
    webhooks,
    work_permits,
    workspace,
)
from app.api.routes.files import router as legacy_files_router
from app.core.config import get_settings
from app.modules.analytics.api import router as analytics_router
from app.modules.branding.api import router as branding_router
from app.modules.budget.api import router as budget_router
from app.modules.budget.reimbursement_api import router as budget_reimbursement_router
from app.modules.client_portal.api import internal_router as portal_requests_router
from app.modules.client_portal.api import router as client_portal_v1_router
from app.modules.export_center.api import router as export_center_router
from app.modules.files.api import router as files_v1_router
from app.modules.headers import api as headers_api
from app.modules.packs import api as packs_v2_api
from app.modules.pdf import api as pdf_api
from app.modules.pipelines import api as pipelines_api
from app.modules.privacy.api import router as privacy_router
from app.modules.replace import api as replace_api
from app.modules.report_builder.api import router as report_builder_router
from app.modules.rules_engine.api import router as rules_engine_router
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
    (contractors.router, {}),
    (dashboard.router, {"tags": ["dashboard"]}),
    (orders.router, {"tags": ["orders"]}),
    (invoices.router, {"tags": ["invoices"]}),
    (npa.router, {"tags": ["npa"]}),
    (ppe.router, {"tags": ["ppe"]}),
    (permits.router, {"tags": ["permits"]}),
    (work_permits.router, {"tags": ["work-permits"]}),
    (medical.router, {"tags": ["medical"]}),
    (journals.router, {"tags": ["journals"]}),
    (risk.router, {"tags": ["risks"]}),
    (risk_enterprise.router, {}),
    (sites.router, {"tags": ["sites"]}),
    (branches.router, {"tags": ["branches"]}),
    (companies.router, {}),
    (persons.router, {}),
    (employees.router, {}),
    (training.router, {"tags": ["training"]}),
    (training_next.router, {}),
    (briefings.router, {}),
    (calendar.router, {}),
    (calendar_views.router, {}),
    (committees.router, {"tags": ["committees"]}),
    (sout.router, {"tags": ["sout"]}),
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
    (operational_dashboard.router, {"tags": ["operational"]}),
    (workspace.router, {}),
    (tenancy.router, {}),
    (outbox_admin.router, {"prefix": "/admin/outbox", "tags": ["outbox"]}),
    (webhooks.router, {}),
    (integration_readiness.router, {}),
    (tenants.router, {}),
    (tenants.admin_router, {}),
    (platform_tenants.router, {}),
    (pwa_sync.router, {}),
    (external_registry.router, {}),
    (reports.router, {"tags": ["reports"]}),
    (data_quality.router, {"tags": ["data-quality"]}),
)

_LEGACY_FILES_ROUTER_REGISTRATION: RouterRegistration = (
    legacy_files_router,
    {"prefix": "/files-legacy", "tags": ["files-legacy"]},
)

DOCUMENT_CORE_ROUTER_REGISTRATIONS: tuple[RouterRegistration, ...] = (
    (documents.router, {"prefix": "/documents", "tags": ["documents"]}),
    (edo_workflow.router, {"tags": ["edo-workflow"]}),
    (approval_signing_v1.router, {"prefix": "/v1", "tags": ["approval-signing-v1"]}),
    (approval_orchestration.router, {"tags": ["approval-orchestration"]}),
    (pep_signing.router, {"tags": ["pep-signing"]}),
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
    (report_builder_router, {"tags": ["report-builder"]}),
    (rules_engine_router, {"tags": ["rules-engine"]}),
    (budget_router, {"tags": ["budget"]}),
    (budget_reimbursement_router, {"tags": ["budget"]}),
    (privacy_router, {"tags": ["privacy"]}),
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
        registrations = ROUTER_GROUPS[group_name]
        if group_name == "operations":
            registrations = _operations_router_registrations()
        _include_registrations(router, registrations)
    return router


def _operations_router_registrations() -> tuple[RouterRegistration, ...]:
    settings = get_settings()
    registrations = list(OPERATIONS_ROUTER_REGISTRATIONS)
    if settings.enable_files_legacy_routes:
        registrations.append(_LEGACY_FILES_ROUTER_REGISTRATION)
    return tuple(registrations)


def _include_registrations(router: APIRouter, registrations: Iterable[RouterRegistration]) -> None:
    for child, kwargs in registrations:
        router.include_router(child, **kwargs)


def describe_router_groups() -> dict[str, list[dict[str, object]]]:
    description: dict[str, list[dict[str, object]]] = {}
    for group_name in ROUTER_GROUP_ORDER:
        registrations = ROUTER_GROUPS[group_name]
        if group_name == "operations":
            registrations = _operations_router_registrations()
        description[group_name] = [
            {
                "prefix": kwargs.get("prefix", ""),
                "tags": list(kwargs.get("tags", [])),
                "routes": len(child.routes),
            }
            for child, kwargs in registrations
        ]
    return description
