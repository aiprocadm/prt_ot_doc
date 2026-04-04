from app.api.app import create_app
from app.api.v1.route_groups import create_public_router, create_tenant_router
from app.core.config import Settings
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
    assert "/files" in tenant_paths
    # Legacy files router still exposes /files/upload alongside modules/files init flow.
    assert "/files/upload" in tenant_paths
    assert "/tasks" in tenant_paths


def test_progressive_model_compat_layers_export_existing_entities() -> None:
    assert Template.__name__ == "Template"
    assert PipelineRun.__name__ == "PipelineRun"
    assert TenantQuota.__name__ == "TenantQuota"


def test_runtime_routes_do_not_collide_on_critical_path_method_pairs() -> None:
    settings = Settings.model_validate(
        {
            "APP_NAME": "RouteRegistryTest",
            "LIBREOFFICE_BIN": "python",
            "SECRET_KEY": "route-registry-secret",
            "APP_CORS_ORIGINS": ["https://frontend.local"],
        }
    )
    app = create_app(settings)

    seen: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = tuple(sorted((getattr(route, "methods", set()) or set()) - {"HEAD", "OPTIONS"}))
        if not path.startswith("/api/v1") or not methods:
            continue
        seen.setdefault((path, methods), []).append(route.endpoint.__module__)

    critical_keys = {
        ("/api/v1/prescriptions", ("GET",)),
        ("/api/v1/prescriptions", ("POST",)),
        ("/api/v1/training/certificates", ("POST",)),
        ("/api/v1/files:upload-init", ("POST",)),
        ("/api/v1/files/records/{file_id}", ("GET",)),
        ("/api/v1/approvals/start", ("POST",)),
        ("/api/v1/edo/messages", ("GET",)),
        ("/api/v1/v1/approvals/tasks", ("GET",)),
    }

    collisions = {
        key: modules
        for key, modules in seen.items()
        if key in critical_keys and len(modules) > 1
    }

    assert collisions == {}


def test_files_modern_and_legacy_routers_registered_under_operations_group() -> None:
    from app.api.v1.route_groups import describe_router_groups

    operations_group = describe_router_groups()["operations"]
    files_registrations = [entry for entry in operations_group if entry["prefix"] == "/files"]

    assert len(files_registrations) == 2
    tag_sets = {tuple(entry["tags"]) for entry in files_registrations}
    assert ("files",) in tag_sets
    assert ("files-legacy",) in tag_sets


def test_openapi_files_paths_are_unique_and_canonical() -> None:
    settings = Settings.model_validate(
        {
            "APP_NAME": "RouteRegistryOpenAPITest",
            "LIBREOFFICE_BIN": "python",
            "SECRET_KEY": "route-registry-openapi-secret",
            "APP_CORS_ORIGINS": ["https://frontend.local"],
        }
    )
    app = create_app(settings)
    paths = app.openapi().get("paths", {})
    files_paths = sorted(path for path in paths if path.startswith("/api/v1/files"))

    assert files_paths
    assert len(files_paths) == len(set(files_paths))
    assert "/api/v1/files/records/{file_id}" in files_paths
