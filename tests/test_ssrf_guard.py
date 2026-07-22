"""Unit tests for the outbound-webhook SSRF guard (SEC-64 §64.3).

Pure guard logic — no network. Hostname resolution is exercised via an injected
fake resolver so the strict/production paths never touch DNS.
"""

from __future__ import annotations

import pytest

from app.core.ssrf_guard import UnsafeWebhookURLError, assert_safe_webhook_url


async def _resolve_private(_host: str) -> list[str]:
    return ["10.0.0.5"]


async def _resolve_public(_host: str) -> list[str]:
    return ["93.184.216.34"]


async def _resolve_mixed(_host: str) -> list[str]:
    # One public, one private — presence of any private address must block.
    return ["93.184.216.34", "192.168.1.10"]


async def _resolve_empty(_host: str) -> list[str]:
    return []


async def _resolve_boom(_host: str) -> list[str]:
    raise OSError("dns down")


@pytest.mark.anyio
@pytest.mark.parametrize("url", ["ftp://example.com/x", "file:///etc/passwd", "", "   "])
async def test_bad_scheme_or_empty_rejected(url: str) -> None:
    with pytest.raises(UnsafeWebhookURLError):
        await assert_safe_webhook_url(url, app_env="production")


@pytest.mark.anyio
async def test_missing_host_rejected() -> None:
    with pytest.raises(UnsafeWebhookURLError):
        await assert_safe_webhook_url("https:///no-host", app_env="production")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "url",
    [
        "https://169.254.169.254/latest/meta-data/",  # cloud metadata (link-local)
        "https://127.0.0.1/hook",  # loopback
        "https://10.0.0.5/hook",  # private A
        "https://192.168.1.1/hook",  # private C
        "https://172.16.0.1/hook",  # private B
        "https://[::1]/hook",  # IPv6 loopback
        "https://[::ffff:10.0.0.1]/hook",  # IPv4-mapped IPv6 private
        "https://0.0.0.0/hook",  # unspecified
        "https://224.0.0.1/hook",  # multicast
    ],
)
async def test_literal_blocked_addresses_rejected(url: str) -> None:
    with pytest.raises(UnsafeWebhookURLError):
        await assert_safe_webhook_url(url, app_env="production")


@pytest.mark.anyio
async def test_literal_private_ip_blocked_even_in_dev() -> None:
    # Literal blocked ranges are rejected in every environment, not just prod.
    with pytest.raises(UnsafeWebhookURLError):
        await assert_safe_webhook_url("http://127.0.0.1:8000/admin", app_env="development")


@pytest.mark.anyio
async def test_prod_requires_https() -> None:
    with pytest.raises(UnsafeWebhookURLError):
        await assert_safe_webhook_url(
            "http://example.com/x", app_env="production", resolver=_resolve_public
        )


@pytest.mark.anyio
async def test_prod_hostname_resolving_to_private_rejected() -> None:
    with pytest.raises(UnsafeWebhookURLError):
        await assert_safe_webhook_url(
            "https://evil.example/x", app_env="production", resolver=_resolve_private
        )


@pytest.mark.anyio
async def test_prod_hostname_mixed_resolution_rejected() -> None:
    with pytest.raises(UnsafeWebhookURLError):
        await assert_safe_webhook_url(
            "https://mixed.example/x", app_env="production", resolver=_resolve_mixed
        )


@pytest.mark.anyio
@pytest.mark.parametrize("resolver", [_resolve_empty, _resolve_boom])
async def test_prod_unresolvable_is_fail_closed(resolver) -> None:
    with pytest.raises(UnsafeWebhookURLError):
        await assert_safe_webhook_url(
            "https://ghost.example/x", app_env="production", resolver=resolver
        )


@pytest.mark.anyio
async def test_prod_hostname_resolving_to_public_allowed() -> None:
    # Must not raise.
    await assert_safe_webhook_url(
        "https://good.example/x", app_env="production", resolver=_resolve_public
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "url",
    ["http://testserver/hook", "https://example.test/hooks", "https://hooks.example/own"],
)
async def test_dev_permissive_for_fake_hosts(url: str) -> None:
    # Dev/test must not resolve fake hosts (no network) and must not raise.
    await assert_safe_webhook_url(url, app_env="development")


@pytest.mark.anyio
async def test_staging_is_strict_like_prod() -> None:
    with pytest.raises(UnsafeWebhookURLError):
        await assert_safe_webhook_url(
            "https://evil.example/x", app_env="staging", resolver=_resolve_private
        )
