from app.api.v1.route_groups import create_public_router, create_tenant_router
from app.models.document_core import PipelineRun, Template
from app.models.tenanting import TenantQuota


def test_route_group_registry_preserves_core_public_and_tenant_paths() -> None:
    public_router = create_public_router()
    tenant_router = create_tenant_router()

    public_paths = {route.path for route in public_router.routes}
    tenant_paths = {route.path for route in tenant_router.routes}

    assert "/auth/login" in public_paths
    assert "/portal/packages" in public_paths
    assert "/findings" in tenant_paths
    assert "/corrective-actions" in tenant_paths
    assert "/files/upload" in tenant_paths or "/files" in tenant_paths
    assert "/tasks" in tenant_paths


def test_progressive_model_compat_layers_export_existing_entities() -> None:
    assert Template.__name__ == "Template"
    assert PipelineRun.__name__ == "PipelineRun"
    assert TenantQuota.__name__ == "TenantQuota"
