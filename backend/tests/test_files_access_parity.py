from __future__ import annotations

from collections.abc import Callable
from inspect import signature
from typing import Annotated, get_args, get_origin

from fastapi.params import Depends

from app.api.routes.files import _FILE_READ_ROLES, _FILE_UPLOAD_ROLES
from app.api.routes.files import download_file as legacy_download_file
from app.api.routes.files import upload_file as legacy_upload_file
from app.modules.files.api import _FILE_READ_ROLES as _CANONICAL_FILE_READ_ROLES
from app.modules.files.api import _FILE_UPLOAD_ROLES as _CANONICAL_FILE_UPLOAD_ROLES
from app.modules.files.api import create_upload_session_v2, get_download_url_v2


def _depends_call_by_parameter(endpoint: Callable[..., object], parameter_name: str) -> object:
    parameter = signature(endpoint).parameters[parameter_name]
    if isinstance(parameter.default, Depends):
        return parameter.default.dependency

    annotation = parameter.annotation
    if get_origin(annotation) is Annotated:
        for metadata in get_args(annotation)[1:]:
            if isinstance(metadata, Depends):
                return metadata.dependency

    raise AssertionError(
        f"Parameter {parameter_name} on {endpoint.__name__} has no Depends() binding"
    )


def test_files_access_roles_read_write_parity() -> None:
    read_roles = set(_FILE_READ_ROLES)
    write_roles = set(_FILE_UPLOAD_ROLES)

    # Any upload-capable role must also be able to read file surfaces.
    assert write_roles.issubset(read_roles)

    # Client portal roles can read files but cannot upload them.
    assert "client_user" in read_roles
    assert "client_user" not in write_roles


def test_canonical_files_roles_match_legacy_contract() -> None:
    assert set(_FILE_READ_ROLES) == set(_CANONICAL_FILE_READ_ROLES)
    assert set(_FILE_UPLOAD_ROLES) == set(_CANONICAL_FILE_UPLOAD_ROLES)


def test_legacy_upload_and_download_dependencies_match_canonical_tenant_and_abac_contract() -> None:
    legacy_upload_tenant_dep = _depends_call_by_parameter(legacy_upload_file, "tenant")
    legacy_upload_access_dep = _depends_call_by_parameter(legacy_upload_file, "access")
    legacy_download_tenant_dep = _depends_call_by_parameter(legacy_download_file, "tenant")
    legacy_download_access_dep = _depends_call_by_parameter(legacy_download_file, "access")

    canonical_upload_tenant_dep = _depends_call_by_parameter(create_upload_session_v2, "tenant")
    canonical_upload_access_dep = _depends_call_by_parameter(create_upload_session_v2, "access")
    canonical_download_tenant_dep = _depends_call_by_parameter(get_download_url_v2, "tenant")
    canonical_download_access_dep = _depends_call_by_parameter(get_download_url_v2, "access")

    # Tenant resolution must be shared between canonical and legacy handlers.
    assert legacy_upload_tenant_dep is canonical_upload_tenant_dep
    assert legacy_download_tenant_dep is canonical_download_tenant_dep

    # ABAC gates must remain compatibility-equivalent between write/read surfaces.
    assert getattr(legacy_upload_access_dep, "__module__", "") == getattr(
        canonical_upload_access_dep, "__module__", ""
    )
    assert getattr(legacy_download_access_dep, "__module__", "") == getattr(
        canonical_download_access_dep, "__module__", ""
    )
