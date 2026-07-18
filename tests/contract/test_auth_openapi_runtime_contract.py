from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from app.api.app import create_app
from app.core.config import Settings

SPEC_PATH = Path("docs/openapi.yaml")
AUTH_PATHS: dict[str, tuple[str, ...]] = {
    "/api/v1/auth/login": ("post",),
    "/api/v1/auth/refresh": ("post",),
    "/api/v1/auth/logout": ("post",),
    "/api/v1/auth/me": ("get",),
    "/api/v1/auth/me/permissions": ("get",),
}


def _load_static_spec() -> dict[str, Any]:
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


def _build_runtime_spec() -> dict[str, Any]:
    settings = Settings.model_validate(
        {
            "APP_NAME": "ContractTest",
            "LIBREOFFICE_BIN": "python",
            "SECRET_KEY": "contract-secret",
            "APP_CORS_ORIGINS": ["https://frontend.local"],
        }
    )
    app = create_app(settings)
    return app.openapi()


def _resolve_local_ref(spec: dict[str, Any], ref: str) -> dict[str, Any]:
    node: Any = spec
    for part in ref.removeprefix("#/").split("/"):
        node = node[part]
    if not isinstance(node, dict):
        raise TypeError(f"Expected object schema for {ref}")
    return node


def _schema_for_response(
    spec: dict[str, Any], path: str, method: str, status_code: str
) -> dict[str, Any]:
    payload = spec["paths"][path][method]["responses"][status_code]
    if isinstance(payload, dict) and isinstance(payload.get("$ref"), str):
        payload = _resolve_local_ref(spec, payload["$ref"])
    schema = payload.get("content", {}).get("application/json", {}).get("schema")
    if not isinstance(schema, dict):
        return {}
    ref = schema.get("$ref")
    return _resolve_local_ref(spec, ref) if isinstance(ref, str) else schema


def _schema_for_request(spec: dict[str, Any], path: str, method: str) -> dict[str, Any]:
    body = spec["paths"][path][method].get("requestBody", {})
    schema = body.get("content", {}).get("application/json", {}).get("schema")
    if not isinstance(schema, dict):
        return {}
    ref = schema.get("$ref")
    return _resolve_local_ref(spec, ref) if isinstance(ref, str) else schema


def _normalize_schema(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"title", "description", "default"}:
                continue
            normalized[key] = _normalize_schema(item)
        return normalized
    if isinstance(value, list):
        return [_normalize_schema(item) for item in value]
    return value


@pytest.mark.contract
def test_auth_paths_exist_in_static_openapi() -> None:
    spec = _load_static_spec()

    for path, methods in AUTH_PATHS.items():
        assert path in spec["paths"], path
        for method in methods:
            assert method in spec["paths"][path], f"{path} {method}"


@pytest.mark.contract
def test_static_auth_openapi_matches_runtime_contract() -> None:
    static_spec = _load_static_spec()
    runtime_spec = _build_runtime_spec()

    for path, methods in AUTH_PATHS.items():
        for method in methods:
            static_operation = static_spec["paths"][path][method]
            runtime_operation = runtime_spec["paths"][path][method]

            static_request = _normalize_schema(_schema_for_request(static_spec, path, method))
            runtime_request = _normalize_schema(_schema_for_request(runtime_spec, path, method))
            assert (
                static_request == runtime_request
            ), f"request schema drift for {method.upper()} {path}"

            static_statuses = set(static_operation["responses"].keys())
            runtime_statuses = set(runtime_operation["responses"].keys())
            assert (
                static_statuses == runtime_statuses
            ), f"response status drift for {method.upper()} {path}"

            for status_code in static_statuses:
                static_response = _normalize_schema(
                    _schema_for_response(static_spec, path, method, status_code)
                )
                runtime_response = _normalize_schema(
                    _schema_for_response(runtime_spec, path, method, status_code)
                )
                if not static_response and not runtime_response:
                    continue
                if not runtime_response and not (
                    status_code.startswith("2") or status_code == "422"
                ):
                    continue
                assert (
                    static_response == runtime_response
                ), f"response schema drift for {method.upper()} {path} {status_code}"
