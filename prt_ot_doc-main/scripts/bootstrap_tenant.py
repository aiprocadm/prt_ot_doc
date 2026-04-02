from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.db.session import AsyncSessionLocal
from app.services.tenants.bootstrap import BootstrapTenantService


ROOT = Path(__file__).resolve().parents[1]
STARTER_PACK_ROOT = ROOT / "seed" / "tenant_starter_packs" / "v1"


def _offline_dry_run_summary(args: argparse.Namespace) -> dict:
    pack = "demo" if args.demo else "default"
    starter_pack = STARTER_PACK_ROOT / f"{pack}.json"
    warnings: list[str] = []
    if not starter_pack.exists():
        warnings.append(f"starter_pack_missing:{starter_pack}")
    warnings.append("database_checks_skipped:offline_dry_run")
    return {
        "tenant_slug": args.tenant,
        "dry_run": True,
        "created": [
            "tenant",
            "tenant_settings",
            "tenant_quota",
            "owner_user",
            "authz_catalog",
            "company_profile",
            "starter_pack",
            "package_presets",
            "audit_event",
        ],
        "reused": [],
        "warnings": warnings,
    }


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

    payload = _offline_dry_run_summary(args) if args.dry_run else asyncio.run(_run(args))
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
