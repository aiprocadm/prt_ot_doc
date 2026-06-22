"""HMAC verification for public inbound webhook endpoints."""

from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import HTTPException, Request, status

from app.core.config import Settings
from app.core.errors import api_problem_detail

logger = logging.getLogger(__name__)

_SIGNATURE_HEADERS = (
    "x-inbound-webhook-signature",
    "x-webhook-signature",
)


def verify_inbound_webhook_body_hmac(
    *, settings: Settings, raw_body: bytes, request: Request
) -> None:
    """If ``INBOUND_WEBHOOK_HMAC_SECRET`` is set, require a matching hex HMAC-SHA256 of the raw body."""

    secret = (getattr(settings, "inbound_webhook_hmac_secret", None) or "").strip()
    if not secret:
        return

    received: str | None = None
    for name in _SIGNATURE_HEADERS:
        value = request.headers.get(name)
        if value:
            received = value.strip()
            break

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

    if received.lower().startswith("sha256="):
        received = received.split("=", 1)[1].strip()

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
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
