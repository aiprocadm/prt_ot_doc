from __future__ import annotations

import asyncio
import sys

from app.db.session import _create_tenant_schema


async def main(slug: str) -> None:
    await _create_tenant_schema(f"tenant_{slug}")
    print(f"Tenant schema tenant_{slug} is ready")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/migrate_tenant.py <slug>")
    asyncio.run(main(sys.argv[1]))
