from __future__ import annotations

import hashlib

import pytest

from app.modules.files.service import compute_sha256_stream
from app.modules.files.storage import assert_tenant_key


def test_compute_sha256_stream_matches_hashlib() -> None:
    chunks = [b"abc", b"123", b"\x00\xff"]
    expected = hashlib.sha256(b"".join(chunks)).hexdigest()
    assert compute_sha256_stream(chunks) == expected


def test_assert_tenant_key_allows_valid_current_prefix() -> None:
    assert_tenant_key(tenant_id="tenant-1", key="tenants/tenant-1/files/abc")


def test_assert_tenant_key_allows_legacy_prefix() -> None:
    assert_tenant_key(tenant_id="tenant-1", key="tenant/tenant-1/files/abc")


def test_assert_tenant_key_rejects_invalid_prefix() -> None:
    with pytest.raises(PermissionError):
        assert_tenant_key(tenant_id="tenant-1", key="tenant/tenant-2/files/abc")


def test_assert_tenant_key_rejects_path_traversal() -> None:
    with pytest.raises(PermissionError):
        assert_tenant_key(tenant_id="tenant-1", key="tenants/tenant-1/files/../tenant-2/leak")
