from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def tenant_s3_key(tenant_id: str, path: str) -> str:
    clean_path = path.lstrip("/")
    return f"tenants/{tenant_id}/{clean_path}"


async def with_tenant_db(session: AsyncSession, tenant_schema: str) -> None:
    await session.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))
