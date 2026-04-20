#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx


@dataclass(slots=True)
class ProbeResult:
    status_code: int
    latency_ms: float


@dataclass(slots=True)
class ProbeSummary:
    path: str
    requests: int
    concurrency: int
    expect_status: int
    success_count: int
    error_count: int
    error_rate: float
    throughput_rps: float
    min_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    statuses: list[int]


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        return 0.0
    rank = max(0, min(len(sorted_values) - 1, round(len(sorted_values) * percentile) - 1))
    return sorted_values[rank]


async def _hit(client: httpx.AsyncClient, path: str, tenant: str | None) -> ProbeResult:
    headers = {"X-Tenant": tenant} if tenant else {}
    started = time.perf_counter()
    response = await client.get(path, headers=headers)
    elapsed = (time.perf_counter() - started) * 1000
    return ProbeResult(status_code=response.status_code, latency_ms=elapsed)


def _check_thresholds(summary: ProbeSummary, args: argparse.Namespace) -> list[str]:
    failures: list[str] = []
    if args.max_error_rate is not None and summary.error_rate > args.max_error_rate:
        failures.append(
            f"error_rate {summary.error_rate:.4f} exceeded max_error_rate {args.max_error_rate:.4f}"
        )
    if args.min_throughput is not None and summary.throughput_rps < args.min_throughput:
        failures.append(
            f"throughput_rps {summary.throughput_rps:.2f} below min_throughput {args.min_throughput:.2f}"
        )
    if args.max_p50_ms is not None and summary.p50_ms > args.max_p50_ms:
        failures.append(f"p50_ms {summary.p50_ms:.1f} exceeded max_p50_ms {args.max_p50_ms:.1f}")
    if args.max_p95_ms is not None and summary.p95_ms > args.max_p95_ms:
        failures.append(f"p95_ms {summary.p95_ms:.1f} exceeded max_p95_ms {args.max_p95_ms:.1f}")
    if args.max_p99_ms is not None and summary.p99_ms > args.max_p99_ms:
        failures.append(f"p99_ms {summary.p99_ms:.1f} exceeded max_p99_ms {args.max_p99_ms:.1f}")
    return failures


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
    parser.add_argument("--max-error-rate", type=float, default=None)
    parser.add_argument("--min-throughput", type=float, default=None)
    parser.add_argument("--max-p50-ms", type=float, default=None)
    parser.add_argument("--max-p95-ms", type=float, default=None)
    parser.add_argument("--max-p99-ms", type=float, default=None)
    parser.add_argument("--output-json", default=None)
    args = parser.parse_args()

    limits = httpx.Limits(
        max_connections=args.concurrency, max_keepalive_connections=args.concurrency
    )
    timeout = httpx.Timeout(15.0)
    results: list[ProbeResult] = []
    errors: list[str] = []
    sem = asyncio.Semaphore(args.concurrency)

    started = time.perf_counter()
    async with httpx.AsyncClient(base_url=args.base_url, limits=limits, timeout=timeout) as client:

        async def worker() -> None:
            async with sem:
                try:
                    results.append(await _hit(client, args.path, args.tenant))
                except Exception as exc:  # noqa: BLE001
                    errors.append(str(exc))

        await asyncio.gather(*(worker() for _ in range(args.requests)))

    elapsed = time.perf_counter() - started

    if not results:
        print("No successful responses recorded.")
        if errors:
            print(f"Errors: {errors[:5]}")
        return 1

    latencies = [item.latency_ms for item in results]
    ordered = sorted(latencies)
    statuses = sorted({item.status_code for item in results})
    throughput_rps = len(results) / elapsed if elapsed > 0 else 0.0
    total_attempted = len(results) + len(errors)
    error_rate = len(errors) / total_attempted if total_attempted else 1.0

    summary = ProbeSummary(
        path=args.path,
        requests=args.requests,
        concurrency=args.concurrency,
        expect_status=args.expect_status,
        success_count=len(results),
        error_count=len(errors),
        error_rate=error_rate,
        throughput_rps=throughput_rps,
        min_ms=min(latencies),
        p50_ms=_percentile(ordered, 0.50),
        p95_ms=_percentile(ordered, 0.95),
        p99_ms=_percentile(ordered, 0.99),
        max_ms=max(latencies),
        statuses=statuses,
    )

    print(
        f"path={summary.path} requests={summary.success_count}/{summary.requests} "
        f"errors={summary.error_count} statuses={summary.statuses}"
    )
    print(
        "latency_ms "
        f"min={summary.min_ms:.1f} p50={summary.p50_ms:.1f} "
        f"p95={summary.p95_ms:.1f} p99={summary.p99_ms:.1f} max={summary.max_ms:.1f}"
    )
    print(
        f"throughput_rps={summary.throughput_rps:.2f} error_rate={summary.error_rate:.4f}"
    )

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(asdict(summary), indent=2) + "\n", encoding="utf-8")

    failures = _check_thresholds(summary, args)
    if statuses != [args.expect_status]:
        failures.append(f"Unexpected response statuses {statuses}, expected {[args.expect_status]}")

    if failures:
        print("threshold_check=FAIL")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("threshold_check=PASS")
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
