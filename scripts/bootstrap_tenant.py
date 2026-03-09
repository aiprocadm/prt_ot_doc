from __future__ import annotations

import argparse
import asyncio
import json

from app.db.session import AsyncSessionLocal
from app.services.tenants.bootstrap import BootstrapTenantService


async def _run(args: argparse.Namespace) -> dict:
    async with AsyncSessionLocal(tenant="public", include_public=False, create_schema=False) as session:
        service = BootstrapTenantService(session)
        summary = await service.run(
            tenant_slug=args.tenant,
            tenant_name=args.name,
            owner_email=args.owner_email,
            owner_password=args.owner_password,
            dry_run=args.dry_run,
            demo=args.demo,
        )
        if not args.dry_run:
            await session.commit()
        return summary.to_dict()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap tenant with starter packs and owner user.")
    parser.add_argument("--tenant", required=True, help="Tenant slug")
    parser.add_argument("--name", required=True, help="Tenant display name")
    parser.add_argument("--owner-email", required=True, help="Owner admin email")
    parser.add_argument("--owner-password", default="ChangeMe123!", help="Owner admin password")
    parser.add_argument("--dry-run", action="store_true", help="Simulate bootstrap without writes")
    parser.add_argument("--demo", action="store_true", help="Use demo starter pack")
    args = parser.parse_args()

    payload = asyncio.run(_run(args))
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
