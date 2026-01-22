"""Helpers for idempotent HTTP request handling."""
from __future__ import annotations

import hashlib
import logging
import json
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select

from app.core.tenant import get_current_tenant
from app.db.session import AsyncSessionLocal
from app.models.models import IdempotencyKey

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

logger = logging.getLogger("app.idempotency")

__all__ = [
    "compute_request_hash",
    "idempotency_dependency",
    "store_idempotent_response",
]


def compute_request_hash(payload: Any) -> str:
    """Return a stable SHA-256 hash for JSON-serializable payloads."""

    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json", exclude_none=True)  # type: ignore[assignment]
    try:
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Payload must be JSON serializable") from exc
    digest = hashlib.sha256(normalized.encode("utf-8"))
    return digest.hexdigest()


async def idempotency_dependency(request: Request) -> Response | None:
    """Return a cached response if the same idempotent request was processed before."""

    method = request.method.upper()
    if method in SAFE_METHODS:
        return None
    key = request.headers.get("Idempotency-Key")
    if key is None:
        return None
    normalized_key = key.strip()
    body = await request.body()
    digest = hashlib.sha256()
    digest.update(method.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(request.url.path.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(body)
    fingerprint = digest.hexdigest()
    request.state.idempotency = {"key": normalized_key, "fingerprint": fingerprint}

    tenant = get_current_tenant()
    try:
        async with AsyncSessionLocal(tenant=tenant.slug) as session:
            session.info["tenant"] = tenant.slug
            stmt = (
                select(IdempotencyKey)
                .where(
                    IdempotencyKey.key == normalized_key,
                    IdempotencyKey.method == method,
                    IdempotencyKey.path == request.url.path,
                )
                .limit(1)
            )
            record = (await session.execute(stmt)).scalar_one_or_none()
    except Exception:  # pragma: no cover - fallback when DB lookup fails
        logger.debug("app.idempotency.lookup_failed", exc_info=True)
        return None
    if record is None:
        return None
    if record.request_hash and record.request_hash != fingerprint:
        raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency key conflict")
    payload = None
    status_code = record.status_code or status.HTTP_200_OK
    if record.response_body:
        try:
            payload = json.loads(record.response_body)
        except json.JSONDecodeError:
            payload = record.response_body
    elif record.result_json:
        stored = dict(record.result_json)
        status_code = int(stored.get("status_code", status_code))
        payload = stored.get("body")
    if payload is None:
        return None
    return JSONResponse(status_code=status_code, content=payload)


async def store_idempotent_response(request: Request, response: Response) -> None:
    """Placeholder hook for updating stored idempotent responses after processing."""

    # Existing endpoints persist idempotent responses explicitly via the service layer.
    # The middleware hook remains for future extensions but performs no work now.
    return None
