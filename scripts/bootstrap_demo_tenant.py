from __future__ import annotations

import argparse
import asyncio

from app.core.config import get_settings
from app.services.demo_bootstrap import bootstrap_demo_tenant


async def _run(force: bool) -> None:
    settings = get_settings()
    if force:
        settings.demo_bootstrap = True
    await bootstrap_demo_tenant(settings)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap demo tenant data")
    parser.add_argument("--force", action="store_true", help="Force-run demo bootstrap in non-demo env")
    args = parser.parse_args()
    asyncio.run(_run(force=args.force))
    print("demo bootstrap completed")


if __name__ == "__main__":
    main()
