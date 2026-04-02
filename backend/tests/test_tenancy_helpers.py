from __future__ import annotations

import pytest

from app.modules.tenancy.helpers import build_search_path


def test_build_search_path_accepts_safe_schema_names() -> None:
    assert build_search_path("tenant_acme") == "tenant_acme,public"


@pytest.mark.parametrize(
    "schema_name",
    [
        "",
        " ",
        "tenant-acme",
        "tenant;drop schema public",
        "tenant.acme",
        "0tenant",
    ],
)
def test_build_search_path_rejects_unsafe_schema_names(schema_name: str) -> None:
    with pytest.raises(ValueError):
        build_search_path(schema_name)
