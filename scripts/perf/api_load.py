#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass

import httpx


@dataclass(slots=True)
class ProbeResult:
    status_code: int
    latency_ms: float


async def _hit(client: httpx.AsyncClient, path: str, tenant: str | None) -> ProbeResult:
    headers = {"X-Tenant": tenant} if tenant else {}
    started = time.perf_counter()
    response = await client.get(path, headers=headers)
    elapsed = (time.perf_counter() - started) * 1000
    return ProbeResult(status_code=response.status_code, latency_ms=elapsed)


async def main_async() -> int:
    parser = argparse.ArgumentParser(
        description="Lightweight async API load probe for RC smoke/perf checks."
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--path", default="/health")
    parser.add_argument("--tenant", default=None)
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--expect-status", type=int, default=200)
    args = parser.parse_args()

    limits = httpx.Limits(
        max_connections=args.concurrency, max_keepalive_connections=args.concurrency
    )
    timeout = httpx.Timeout(15.0)
    results: list[ProbeResult] = []
    errors: list[str] = []
    sem = asyncio.Semaphore(args.concurrency)

    async with httpx.AsyncClient(base_url=args.base_url, limits=limits, timeout=timeout) as client:

        async def worker() -> None:
            async with sem:
                try:
                    results.append(await _hit(client, args.path, args.tenant))
                except Exception as exc:  # noqa: BLE001
                    errors.append(str(exc))

        await asyncio.gather(*(worker() for _ in range(args.requests)))

    if not results:
        print("No successful responses recorded.")
        if errors:
            print(f"Errors: {errors[:5]}")
        return 1

    latencies = [item.latency_ms for item in results]
    statuses = {item.status_code for item in results}
    p95_index = max(0, min(len(latencies) - 1, round(len(latencies) * 0.95) - 1))
    ordered = sorted(latencies)
    print(f"requests={len(results)} errors={len(errors)} statuses={sorted(statuses)}")
    print(
        "latency_ms "
        f"min={min(latencies):.1f} avg={statistics.fmean(latencies):.1f} "
        f"p95={ordered[p95_index]:.1f} max={max(latencies):.1f}"
    )
    if errors:
        print(f"sample_errors={errors[:5]}")
    if statuses != {args.expect_status}:
        return 1
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
