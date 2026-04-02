from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_SCHEMA_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def tenant_s3_key(tenant_id: str, path: str) -> str:
    clean_path = path.lstrip("/")
    return f"tenants/{tenant_id}/{clean_path}"


def build_search_path(schema_name: str) -> str:
    normalized = str(schema_name or "").strip().lower()
    if not _SCHEMA_NAME_RE.fullmatch(normalized):
        raise ValueError("Invalid tenant schema name")
    return f"{normalized},public"


async def with_tenant_db(session: AsyncSession, tenant_schema: str) -> None:
    search_path = build_search_path(tenant_schema)
    await session.execute(text("select set_config('search_path', :search_path, true)"), {"search_path": search_path})
