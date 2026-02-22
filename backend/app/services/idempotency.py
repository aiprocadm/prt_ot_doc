"""Helpers for managing idempotent API requests."""

from __future__ import annotations

import json
from typing import Any, TypeVar

from fastapi import HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import Select, delete, select
from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import IdempotencyKey, IdempotencyStatus

TModel = TypeVar("TModel", bound=BaseModel)


def normalize_idempotency_key(value: str | None) -> str:
    """Validate and normalize an idempotency key value."""

    if value is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Idempotency-Key header is required"
        )
    candidate = value.strip()
    if not candidate:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Idempotency-Key cannot be blank")
    if len(candidate) > 128:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Idempotency-Key is too long")
    return candidate


class IdempotencyService:
    """Persist and restore responses for idempotent HTTP endpoints."""

    def __init__(self, *, session: AsyncSession, tenant_id: str, endpoint: str) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.endpoint = endpoint

    def _base_query(self, *, key: str) -> Select[tuple[IdempotencyKey]]:
        return select(IdempotencyKey).where(
            IdempotencyKey.tenant_id == self.tenant_id,
            IdempotencyKey.endpoint == self.endpoint,
            IdempotencyKey.key == key,
        )

    async def get(self, *, key: str) -> IdempotencyKey | None:
        result = await self.session.execute(self._base_query(key=key))
        return result.scalar_one_or_none()

    async def acquire(
        self,
        *,
        key: str,
        request_hash: str | None = None,
        method: str | None = None,
        path: str | None = None,
    ) -> tuple[IdempotencyKey, bool]:
        existing = await self.get(key=key)
        if existing is not None:
            if request_hash and existing.request_hash and existing.request_hash != request_hash:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    {"code": "idempotency_conflict", "type": "idempotency", "message": "Idempotency key conflict"},
                )
            if request_hash and not existing.request_hash:
                existing.request_hash = request_hash
            if method and not existing.method:
                existing.method = method
            if path and not existing.path:
                existing.path = path
            return existing, False

        record = IdempotencyKey(
            tenant_id=self.tenant_id,
            endpoint=self.endpoint,
            key=key,
            status=IdempotencyStatus.PENDING,
            request_hash=request_hash,
            method=method,
            path=path,
        )
        self.session.add(record)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            recovered = await self.get(key=key)
            if recovered is None:  # pragma: no cover - defensive branch
                raise
            return recovered, False
        return record, True

    async def store_success(
        self,
        record: IdempotencyKey,
        *,
        status_code: int,
        body: dict[str, Any],
    ) -> IdempotencyKey:
        record.status = IdempotencyStatus.SUCCEEDED
        record.status_code = int(status_code)
        record.response_body = json.dumps(body, ensure_ascii=False)
        record.result_json = {
            "status_code": int(status_code),
            "body": body,
        }
        await self.session.flush()
        return record

    async def store_failure(
        self,
        record: IdempotencyKey,
        *,
        status_code: int,
        detail: Any,
    ) -> IdempotencyKey:
        payload = detail
        if isinstance(detail, BaseModel):
            payload = detail.model_dump()
        elif isinstance(detail, (dict, list, str, int, float, bool)) or detail is None:
            payload = detail
        else:
            payload = str(detail)
        record.status = IdempotencyStatus.FAILED
        record.status_code = int(status_code)
        record.response_body = json.dumps(payload, ensure_ascii=False)
        record.result_json = {
            "status_code": int(status_code),
            "body": payload,
        }
        await self.session.flush()
        return record

    async def respond_from_store(
        self,
        record: IdempotencyKey,
        *,
        model: type[TModel],
        response: Response | None = None,
    ) -> TModel:
        """Build a response from a stored idempotency record."""

        status_code = record.status_code or status.HTTP_200_OK
        if record.response_body:
            try:
                body = json.loads(record.response_body)
            except json.JSONDecodeError:
                body = record.response_body
        else:
            payload = record.result_json or {}
            status_code = int(payload.get("status_code", status_code))
            body = payload.get("body", {})
        if response is not None:
            response.status_code = status_code

        if record.status is IdempotencyStatus.SUCCEEDED:
            return model.model_validate(body)

        if isinstance(body, dict) and "detail" in body:
            raise HTTPException(status_code, body["detail"])
        raise HTTPException(status_code, body)

    async def update_document_version_id(
        self,
        *,
        key: str,
        document_version_id: str,
    ) -> None:
        record = await self.get(key=key)
        if record is None or record.status is not IdempotencyStatus.SUCCEEDED:
            return

        body: dict[str, Any] = {}
        if record.response_body:
            try:
                body = json.loads(record.response_body)
            except json.JSONDecodeError:
                body = {}
        if not body:
            body = dict((record.result_json or {}).get("body") or {})
        if body.get("document_version_id") == document_version_id:
            return

        body["document_version_id"] = document_version_id
        record.response_body = json.dumps(body, ensure_ascii=False)
        status_code = record.status_code or status.HTTP_200_OK
        record.result_json = {"status_code": int(status_code), "body": body}
        await self.session.flush()


async def cleanup_idempotency_keys(
    *,
    session: AsyncSession,
    ttl_days: int,
) -> int:
    """Remove completed idempotency records older than the configured TTL."""

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=ttl_days)
    stmt = (
        delete(IdempotencyKey)
        .where(IdempotencyKey.updated_at < cutoff)
        .where(IdempotencyKey.status.in_([IdempotencyStatus.SUCCEEDED, IdempotencyStatus.FAILED]))
    )
    result = await session.execute(stmt)
    await session.flush()
    return int(result.rowcount or 0)
