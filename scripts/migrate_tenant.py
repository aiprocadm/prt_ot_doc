from __future__ import annotations

import asyncio
import sys

from app.db.session import _create_tenant_schema, resolve_tenant_schema


async def main(tenant: str) -> None:
    schema = resolve_tenant_schema(tenant)
    await _create_tenant_schema(schema)
    print(f"Tenant schema {schema} is ready")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/migrate_tenant.py <tenant_id>")
    asyncio.run(main(sys.argv[1]))
