"""Fail-closed HMAC verification for public / unauthenticated inbound webhook receivers.

These endpoints are reachable with only an ``X-Tenant`` header — they sit on the
``TenantMiddleware`` public allowlist (``/webhooks/inbound``, ``/edo/webhooks``,
``/edo/webhook/status``) or carry no RBAC dependency (``/webhooks/edo``,
``/webhooks/sign``). The HMAC signature over the raw request body is therefore the ONLY
thing authenticating the caller.

Verification fails **closed**: an endpoint with no configured secret cannot authenticate
anyone and MUST reject every request rather than accept an anonymous, state-mutating
write. This is deliberately stricter than the historical "verify only when a secret is
set" behaviour, which silently disabled the guard whenever config was missing.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import HTTPException, Request, status

from app.core.config import Settings
from app.core.errors import api_problem_detail

logger = logging.getLogger(__name__)

# Header aliases carrying the hex HMAC-SHA256 of the raw body for the global receiver.
GLOBAL_SIGNATURE_HEADERS = (
    "x-inbound-webhook-signature",
    "x-webhook-signature",
)


def _extract_signature(request: Request, signature_headers: tuple[str, ...]) -> str | None:
    for name in signature_headers:
        value = request.headers.get(name)
        if value:
            received = value.strip()
            if received.lower().startswith("sha256="):
                received = received.split("=", 1)[1].strip()
            return received
    return None


def enforce_webhook_hmac(
    *,
    raw_body: bytes,
    request: Request,
    secret: str | None,
    signature_headers: tuple[str, ...] = GLOBAL_SIGNATURE_HEADERS,
) -> None:
    """Require a matching hex HMAC-SHA256 of ``raw_body``; fail closed when unverifiable.

    Args:
        raw_body: The exact bytes the caller sent — the HMAC is computed over these, not
            over a re-serialized parsed payload (re-serialization reorders keys and breaks
            the signature).
        request: Inbound request; the signature header is read from it.
        secret: Signing secret (global or per-tenant). Empty/absent -> reject.
        signature_headers: Header names to read the signature from, in priority order.

    Raises:
        HTTPException: 401 ``WEBHOOK_SECRET_NOT_CONFIGURED`` when no secret is configured
            (fail closed); 401 ``WEBHOOK_SIGNATURE_REQUIRED`` when the secret is set but no
            signature header is present; 403 ``WEBHOOK_SIGNATURE_INVALID`` on mismatch.
    """

    normalized_secret = (secret or "").strip()
    if not normalized_secret:
        logger.warning(
            "inbound_webhook.secret_not_configured",
            extra={"path": request.url.path},
        )
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=api_problem_detail(
                code="WEBHOOK_SECRET_NOT_CONFIGURED",
                message="Inbound webhook signing secret is not configured; refusing anonymous write",
                error_type="security",
            ),
        )

    received = _extract_signature(request, signature_headers)
    if not received:
        logger.warning(
            "inbound_webhook.signature_missing",
            extra={"path": request.url.path},
        )
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=api_problem_detail(
                code="WEBHOOK_SIGNATURE_REQUIRED",
                message="Inbound webhook signature is required",
                error_type="security",
            ),
        )

    expected = hmac.new(normalized_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if len(received) != len(expected) or not hmac.compare_digest(
        received.lower(), expected.lower()
    ):
        logger.warning(
            "inbound_webhook.signature_mismatch",
            extra={"path": request.url.path},
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=api_problem_detail(
                code="WEBHOOK_SIGNATURE_INVALID",
                message="Inbound webhook signature is invalid",
                error_type="security",
            ),
        )


def verify_inbound_webhook_body_hmac(
    *, settings: Settings, raw_body: bytes, request: Request
) -> None:
    """Fail-closed HMAC gate keyed on the global ``INBOUND_WEBHOOK_HMAC_SECRET`` setting."""

    enforce_webhook_hmac(
        raw_body=raw_body,
        request=request,
        secret=getattr(settings, "inbound_webhook_hmac_secret", None),
        signature_headers=GLOBAL_SIGNATURE_HEADERS,
    )
