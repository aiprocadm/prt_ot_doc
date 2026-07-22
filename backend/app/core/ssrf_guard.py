"""SSRF guard for outbound webhooks (SEC-64 §64.3).

Outbound webhooks let a tenant/admin point the server at an arbitrary URL. Without
a guard, that URL can target internal surfaces — cloud metadata (169.254.169.254),
loopback admin ports, private subnets — and the server dutifully fetches them
(classic SSRF). This module rejects such targets *before* the HTTP call.

Depth: literal IPs are range-checked directly; hostnames are resolved (all A/AAAA
records) and every resolved address is checked. Strictness is environment-aware —
strict + fail-closed in production/staging, permissive in development/test (webhook
tests post to non-resolving fake hosts like ``http://testserver`` and must not hit
the network). See ``docs/superpowers/specs/2026-07-22-sec64-webhook-ssrf-guard-design.md``.

Known limitation: resolution happens immediately before dispatch but the connection
is not pinned to the validated IP, so a DNS-rebinding TOCTOU window remains. Full
IP-pinning via a custom httpx transport is a documented follow-up (non-goal here).
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

_STRICT_ENVS = ("production", "staging")

# Resolver: hostname -> list of IP strings. Injectable so tests never touch the network.
Resolver = Callable[[str], Awaitable[list[str]]]


class UnsafeWebhookURLError(ValueError):
    """Raised when a webhook target URL resolves to a disallowed address."""


def _normalize(ip: ipaddress.IPv4Address | ipaddress.IPv6Address):
    """Unwrap IPv4-mapped IPv6 (``::ffff:10.0.0.1``) so the wrapper can't smuggle a
    private IPv4 past the range check."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    ip = _normalize(ip)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Return the parsed IP if ``host`` is a literal address, else ``None``.

    Handles bracketed IPv6 literals (``[::1]``) already stripped by ``urlsplit``.
    """
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


async def _default_resolver(host: str) -> list[str]:
    infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
    # getaddrinfo tuples: (family, type, proto, canonname, sockaddr); sockaddr[0] is the IP.
    return [info[4][0] for info in infos if info[4] and info[4][0]]


async def assert_safe_webhook_url(
    url: str,
    *,
    app_env: str,
    resolver: Resolver | None = None,
) -> None:
    """Raise :class:`UnsafeWebhookURLError` if ``url`` is an unsafe webhook target.

    Strict (production/staging): https required, hostnames resolved, every resolved
    address range-checked, unresolvable → rejected (fail-closed). Non-strict
    (development/test): scheme/host still validated and *literal* private IPs still
    rejected, but hostnames are not resolved (permissive, no network in tests).
    """
    raw = (url or "").strip()
    if not raw:
        raise UnsafeWebhookURLError("webhook URL is empty")

    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise UnsafeWebhookURLError(f"webhook URL scheme must be http or https, got {scheme!r}")

    host = parts.hostname  # already lowercased, brackets stripped for IPv6
    if not host:
        raise UnsafeWebhookURLError("webhook URL has no host")

    strict = app_env in _STRICT_ENVS

    if strict and scheme != "https":
        raise UnsafeWebhookURLError("webhook URL must use https in production/staging")

    literal = _parse_ip(host)
    if literal is not None:
        # Literal IPs are always range-checked, in every environment.
        if _ip_is_blocked(literal):
            raise UnsafeWebhookURLError(f"webhook URL targets a disallowed address: {host}")
        return

    if not strict:
        # Non-resolving fake hosts are common in dev/test; don't touch the network.
        return

    resolve = resolver or _default_resolver
    try:
        addresses = await resolve(host)
    except Exception as exc:  # DNS failure, timeout, etc.
        raise UnsafeWebhookURLError(f"webhook host {host!r} did not resolve") from exc

    if not addresses:
        raise UnsafeWebhookURLError(f"webhook host {host!r} resolved to no addresses")

    for addr in addresses:
        parsed = _parse_ip(addr)
        if parsed is None:
            # Unparseable resolver output — treat as unsafe (fail-closed).
            raise UnsafeWebhookURLError(f"webhook host {host!r} resolved to unparseable {addr!r}")
        if _ip_is_blocked(parsed):
            raise UnsafeWebhookURLError(
                f"webhook host {host!r} resolves to a disallowed address: {addr}"
            )
