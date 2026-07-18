"""Utilities for managing tenant-scoped API keys."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ApiKey

API_KEY_PREFIX = "ak"
API_KEY_DELIMITER = "."
DEFAULT_SCOPE = "api:read"


def _hash_secret(secret: str) -> str:
    digest = hashlib.sha256()
    digest.update(secret.encode("utf-8"))
    return digest.hexdigest()


def _normalize_scopes(scopes: Sequence[str] | str | None) -> str:
    if scopes is None:
        return DEFAULT_SCOPE
    if isinstance(scopes, str):
        tokens = scopes.replace(",", " ").split()
    else:
        tokens = []  # list[str]
        for scope in scopes:
            tokens.extend(str(scope).replace(",", " ").split())
    unique = []
    seen = set()
    for token in tokens:
        if not token:
            continue
        normalized = token.strip().lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return " ".join(unique) if unique else DEFAULT_SCOPE


def _format_key(prefix: str, secret: str) -> str:
    return f"{API_KEY_PREFIX}_{prefix}{API_KEY_DELIMITER}{secret}"


def _parse_key(value: str) -> tuple[str, str] | None:
    if not value or not value.startswith(f"{API_KEY_PREFIX}_"):
        return None
    try:
        payload = value[len(API_KEY_PREFIX) + 1 :]
        prefix, secret = payload.split(API_KEY_DELIMITER, 1)
    except ValueError:
        return None
    if not prefix or not secret:
        return None
    return prefix, secret


async def _generate_unique_prefix(session: AsyncSession) -> str:
    for _ in range(20):
        candidate = secrets.token_urlsafe(6)
        result = await session.execute(select(ApiKey).where(ApiKey.key_prefix == candidate))
        if result.scalar_one_or_none() is None:
            return candidate
    raise RuntimeError("Failed to generate a unique API key prefix")


@dataclass(slots=True)
class ApiKeySecret:
    record: ApiKey
    value: str


async def create_api_key(
    session: AsyncSession,
    *,
    tenant_id: str,
    name: str,
    scopes: Sequence[str] | str | None = None,
    is_active: bool = True,
) -> ApiKeySecret:
    prefix = await _generate_unique_prefix(session)
    secret = secrets.token_urlsafe(32)
    scope_string = _normalize_scopes(scopes)
    hashed = _hash_secret(secret)

    record = ApiKey(
        tenant_id=tenant_id,
        name=name,
        key_prefix=prefix,
        key_hash=hashed,
        scopes=scope_string,
        is_active=is_active,
    )
    session.add(record)
    await session.flush()
    key_value = _format_key(prefix, secret)
    await session.commit()
    await session.refresh(record)
    return ApiKeySecret(record=record, value=key_value)


async def rotate_api_key(
    session: AsyncSession,
    *,
    record: ApiKey,
) -> ApiKeySecret:
    record.is_active = False
    record.revoked_at = datetime.now(timezone.utc)
    record.last_rotated_at = record.revoked_at
    session.add(record)
    await session.flush()
    return await create_api_key(
        session,
        tenant_id=str(record.tenant_id),
        name=f"{record.name}-rotated-{int(record.last_rotated_at.timestamp())}",
        scopes=record.scope_list,
        is_active=True,
    )


async def get_api_key_by_prefix(session: AsyncSession, prefix: str) -> ApiKey | None:
    result = await session.execute(select(ApiKey).where(ApiKey.key_prefix == prefix))
    return result.scalar_one_or_none()


async def authenticate_api_key(session: AsyncSession, token: str) -> ApiKey | None:
    parsed = _parse_key(token)
    if not parsed:
        return None
    prefix, secret = parsed
    record = await get_api_key_by_prefix(session, prefix)
    if record is None or not record.is_active or record.revoked_at is not None:
        return None
    candidate = _hash_secret(secret)
    if not hmac.compare_digest(record.key_hash, candidate):
        return None
    record.last_used_at = datetime.now(timezone.utc)
    record.usage_count = int(record.usage_count or 0) + 1
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


def mask_api_key(value: str, visible: int = 4) -> str:
    if visible <= 0:
        return "***"
    prefix = value[:-visible]
    suffix = value[-visible:]
    return f"{'*' * len(prefix)}{suffix}"


__all__ = [
    "API_KEY_PREFIX",
    "API_KEY_DELIMITER",
    "ApiKeySecret",
    "authenticate_api_key",
    "create_api_key",
    "get_api_key_by_prefix",
    "mask_api_key",
    "rotate_api_key",
]
