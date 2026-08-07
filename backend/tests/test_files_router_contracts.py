from fastapi.routing import APIRoute

from app.api.app import create_app
from app.core.config import Settings
from app.modules.files.api import router


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "APP_NAME": "FilesRouterContracts",
            "LIBREOFFICE_BIN": "python",
            "SECRET_KEY": "files-router-contracts-secret",
            "APP_CORS_ORIGINS": ["https://frontend.local"],
        }
    )


def test_files_router_registers_canonical_and_legacy_compat_aliases() -> None:
    routes = [r for r in router.routes if isinstance(r, APIRoute)]
    by_path_method = {
        (route.path, method)
        for route in routes
        for method in (route.methods or set()) - {"HEAD", "OPTIONS"}
    }

    assert ("/presign-upload", "POST") in by_path_method
    assert ("/init-upload", "POST") in by_path_method
    assert ("/{file_id}:link", "POST") in by_path_method
    assert ("/{file_id}/link", "POST") in by_path_method
    assert ("/entities/{entity_type}/{entity_id}/files", "GET") in by_path_method
    assert ("/entities/{entity_type}/{entity_id}/list", "GET") in by_path_method
    assert ("/{file_id}:signed-url", "POST") in by_path_method
    assert ("/{file_id}/signed-url", "POST") in by_path_method


def test_files_router_operation_ids_are_unique_and_stable() -> None:
    operation_ids = [
        route.operation_id
        for route in router.routes
        if isinstance(route, APIRoute) and route.operation_id
    ]

    assert len(operation_ids) == len(set(operation_ids))
    assert "files_presign_upload" in operation_ids
    assert "files_init_upload_legacy_compat" in operation_ids
    assert "files_link" in operation_ids
    assert "files_link_legacy_compat" in operation_ids


def test_openapi_includes_canonical_and_compat_files_paths_under_api_v1() -> None:
    app = create_app(_settings())
    files_paths = {
        path for path in app.openapi().get("paths", {}) if path.startswith("/api/v1/files")
    }

    assert "/api/v1/files/presign-upload" in files_paths
    assert "/api/v1/files/init-upload" in files_paths
    assert "/api/v1/files/{file_id}:link" in files_paths
    assert "/api/v1/files/{file_id}/link" in files_paths
