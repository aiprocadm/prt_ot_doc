"""Helpers for idempotent HTTP request handling."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select

from app.core.tenant import get_current_tenant
from app.db.session import AsyncSessionLocal
from app.models.models import IdempotencyKey, IdempotencyStatus

IDEMPOTENT_METHODS = {"POST", "PUT", "PATCH"}
MAX_STORED_BODY_BYTES = 256 * 1024

logger = logging.getLogger("app.idempotency")

__all__ = [
    "canonical_json",
    "compute_request_hash",
    "idempotency_dependency",
    "store_idempotent_response",
]


def canonical_json(payload: Any) -> str:
    """Serialize JSON payload in canonical deterministic form."""

    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json", exclude_none=True)  # type: ignore[assignment]
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Payload must be JSON serializable") from exc


def compute_request_hash(payload: Any) -> str:
    """Return a stable SHA-256 hash for JSON-serializable payloads."""

    normalized = canonical_json(payload)
    digest = hashlib.sha256(normalized.encode("utf-8"))
    return digest.hexdigest()


async def idempotency_dependency(request: Request) -> Response | None:
    """Return a cached response if the same idempotent request was processed before."""

    method = request.method.upper()
    if method not in IDEMPOTENT_METHODS:
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
    digest.update(str(request.url.query).encode("utf-8"))
    digest.update(b"\x00")
    digest.update((request.headers.get("content-type") or "").encode("utf-8"))
    digest.update(b"\x00")
    tenant = get_current_tenant()
    tenant_id = getattr(getattr(request, "state", None), "tenant_id", None) or tenant.slug
    digest.update(str(tenant_id).encode("utf-8"))
    digest.update(b"\x00")
    digest.update(body)
    fingerprint = digest.hexdigest()
    request.state.idempotency = {"key": normalized_key, "fingerprint": fingerprint}

    try:
        async with AsyncSessionLocal(tenant=tenant.slug) as session:
            session.info["tenant"] = tenant.slug
            stmt = (
                select(IdempotencyKey)
                .where(
                    IdempotencyKey.key == normalized_key,
                    IdempotencyKey.tenant_id == str(tenant_id),
                    IdempotencyKey.endpoint == request.url.path,
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
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "code": "IDEMPOTENCY_CONFLICT",
                "type": "idempotency",
                "message": "Idempotency key conflict",
            },
        )
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

    state = getattr(request, "state", None)
    idem = getattr(state, "idempotency", None) if state is not None else None
    if not isinstance(idem, dict):
        return None

    key = str(idem.get("key") or "").strip()
    fingerprint = str(idem.get("fingerprint") or "").strip()
    if not key or not fingerprint:
        return None

    tenant = get_current_tenant()
    tenant_id = getattr(getattr(request, "state", None), "tenant_id", None) or tenant.slug
    try:
        async with AsyncSessionLocal(tenant=tenant.slug) as session:
            session.info["tenant"] = tenant.slug
            stmt = (
                select(IdempotencyKey)
                .where(
                    IdempotencyKey.key == key,
                    IdempotencyKey.tenant_id == str(tenant_id),
                    IdempotencyKey.endpoint == request.url.path,
                    IdempotencyKey.method == request.method.upper(),
                    IdempotencyKey.path == request.url.path,
                )
                .limit(1)
            )
            record = (await session.execute(stmt)).scalar_one_or_none()
            if record is None:
                return None
            if record.request_hash and record.request_hash != fingerprint:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    {
                        "code": "IDEMPOTENCY_CONFLICT",
                        "type": "idempotency",
                        "message": "Idempotency key conflict",
                    },
                )

            record.request_hash = fingerprint
            record.status = IdempotencyStatus.SUCCEEDED
            record.status_code = int(getattr(response, "status_code", status.HTTP_200_OK))
            body = None
            if hasattr(response, "body") and response.body:
                try:
                    body = response.body.decode("utf-8")
                except Exception:
                    body = None
            if body and len(body.encode("utf-8")) > MAX_STORED_BODY_BYTES:
                raise HTTPException(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    {
                        "code": "RESOURCES_EXCEEDED",
                        "type": "resource",
                        "message": "Idempotent response body too large",
                    },
                )
            if body:
                record.response_body = body
            record.response_headers = {
                "Content-Type": getattr(response, "media_type", "application/json")
            }
            await session.commit()
    except Exception:  # pragma: no cover - best-effort persistence
        logger.debug("app.idempotency.store_failed", exc_info=True)
    return None
