from __future__ import annotations

import pytest
from fastapi import HTTPException, status

from app.core import tenant


def test_tenant_schema_helpers() -> None:
    info = tenant.TenantInfo(slug="acme")
    assert tenant.tenant_schema("acme") == "tenant_acme"
    assert tenant.tenant_prefix_path("acme") == "acme"
    assert info.schema == "tenant_acme"
    assert info.s3_prefix == "acme"


def test_tenant_required_validates_presence() -> None:
    with pytest.raises(HTTPException) as exc_info:
        tenant.tenant_required(None)
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

    result = tenant.tenant_required(" ACME ")
    assert result.slug == "acme"


def test_set_current_tenant_updates_context(monkeypatch: pytest.MonkeyPatch) -> None:
    original = tenant.get_current_tenant().slug
    updated = tenant.set_current_tenant("Beta-ORG")
    assert updated.slug == "beta-org"
    assert tenant.get_current_tenant().slug == "beta-org"
    # Reset to original value for subsequent tests.
    tenant.set_current_tenant(original)


def test_tenant_context_restores_previous_value() -> None:
    tenant.set_current_tenant("primary")
    outer = tenant.get_current_tenant().slug

    with tenant.tenant_context("Second") as info:
        assert info.slug == "second"
        assert tenant.get_current_tenant().slug == "second"

    assert tenant.get_current_tenant().slug == outer


@pytest.mark.parametrize(
    "value, expected_status, expected_message",
    [
        ("", status.HTTP_400_BAD_REQUEST, "Tenant slug is required"),
        (" ", status.HTTP_400_BAD_REQUEST, "Tenant slug is required"),
        ("A" * 65, status.HTTP_400_BAD_REQUEST, "Tenant slug is too long"),
        ("invalid!", status.HTTP_400_BAD_REQUEST, "Tenant slug has invalid characters"),
    ],
)
def test_normalize_slug_errors(value: str, expected_status: int, expected_message: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        tenant.set_current_tenant(value)
    assert exc_info.value.status_code == expected_status
    assert expected_message in exc_info.value.detail
