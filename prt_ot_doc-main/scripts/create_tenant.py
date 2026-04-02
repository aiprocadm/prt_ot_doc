from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.models import Tenant, TenantQuota


async def main(slug: str, name: str, email: str) -> None:
    async with AsyncSessionLocal(tenant="public", include_public=False, create_schema=False) as session:
        existing = (await session.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one_or_none()
        if existing:
            print(f"Tenant {slug} already exists")
            return
        tenant = Tenant(slug=slug, code=slug, name=name, contact_email=email, kind="customer", schema_name=f"tenant_{slug}")
        session.add(tenant)
        session.add(TenantQuota(tenant_id=tenant.id))
        await session.commit()
        print(f"Created tenant {slug} ({tenant.id})")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: python scripts/create_tenant.py <slug> <name> <email>")
    asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3]))
