from __future__ import annotations

import pytest

from app.core.integration_url_validation import (
    UnsafeIntegrationURLError,
    assert_safe_http_base_url,
)


def test_rejects_private_ipv4() -> None:
    with pytest.raises(UnsafeIntegrationURLError):
        assert_safe_http_base_url("https://10.0.0.1/api", app_env="test")


def test_rejects_link_local() -> None:
    with pytest.raises(UnsafeIntegrationURLError):
        assert_safe_http_base_url("http://169.254.169.254/latest/meta-data", app_env="test")


def test_allows_public_https() -> None:
    assert_safe_http_base_url("https://edo.vendor.example/v1", app_env="production")


def test_production_requires_https_for_non_loopback() -> None:
    with pytest.raises(UnsafeIntegrationURLError):
        assert_safe_http_base_url("http://edo.vendor.example", app_env="production")


def test_production_allows_https() -> None:
    assert_safe_http_base_url("https://edo.vendor.example", app_env="production")
