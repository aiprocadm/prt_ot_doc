from __future__ import annotations

from app.domains.files.utils import build_storage_key


def test_s3_key_builder_is_tenant_scoped() -> None:
    key_a = build_storage_key(tenant_slug="tenant-a", sha256_hex="a" * 64, extension="pdf")
    key_b = build_storage_key(tenant_slug="tenant-b", sha256_hex="a" * 64, extension="pdf")

    assert key_a.startswith("tenants/tenant-a/")
    assert key_b.startswith("tenants/tenant-b/")
    assert key_a != key_b
