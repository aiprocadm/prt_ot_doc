"""Guardrails for outbound integration base URLs (SSRF mitigation)."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

_BLOCKED_HOSTNAMES = frozenset(
    {
        "metadata.google.internal",
        "metadata.goog",
    }
)


class UnsafeIntegrationURLError(ValueError):
    """Raised when an integration base URL is not allowed."""


def assert_safe_http_base_url(
    url: str,
    *,
    app_env: str,
    allow_http_localhost: bool = True,
) -> None:
    """Reject obviously unsafe base URLs for server-side HTTP clients.

    - Non-http(s) schemes are rejected.
    - Hostnames that parse as private/link-local/multicast/reserved IPv4/IPv6 are rejected.
    - ``metadata.*`` style hostnames used for cloud metadata are rejected.
    - In ``production`` and ``staging``, only ``https`` is allowed unless host is loopback.
    """

    raw = (url or "").strip()
    if not raw:
        raise UnsafeIntegrationURLError("Integration base URL is empty")

    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeIntegrationURLError("Integration base URL must use http or https")

    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise UnsafeIntegrationURLError("Integration base URL must include a host")

    if host in _BLOCKED_HOSTNAMES or host.endswith(".internal"):
        raise UnsafeIntegrationURLError("Integration base URL host is not allowed")

    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise UnsafeIntegrationURLError(
                "Integration base URL must not target a private or link-local address"
            )
        if ip.is_loopback and parsed.scheme != "https" and app_env in ("production", "staging"):
            # Loopback over http only in dev/test
            raise UnsafeIntegrationURLError(
                "Integration base URL must use https in this environment"
            )
    except ValueError:
        # Not a literal IP; hostname labels — block obvious numeric private forms
        if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", host):
            raise UnsafeIntegrationURLError(
                "Integration base URL must not use ambiguous numeric hosts"
            )

    if app_env in ("production", "staging") and parsed.scheme == "http":
        if not (allow_http_localhost and host in ("localhost", "127.0.0.1", "::1")):
            raise UnsafeIntegrationURLError(
                "Integration base URL must use https in production and staging"
            )
