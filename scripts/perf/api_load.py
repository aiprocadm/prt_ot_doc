#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

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


def _render_template(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        rendered = value
        for key, raw in context.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(raw))
        return rendered
    if isinstance(value, list):
        return [_render_template(item, context) for item in value]
    if isinstance(value, dict):
        return {k: _render_template(v, context) for k, v in value.items()}
    return value


def _extract_json_path(payload: Any, path: str) -> Any:
    value = payload
    for segment in path.split("."):
        if isinstance(value, dict):
            value = value.get(segment)
        elif isinstance(value, list) and segment.isdigit():
            idx = int(segment)
            if idx < 0 or idx >= len(value):
                return None
            value = value[idx]
        else:
            return None
    return value


async def _hit(
    client: httpx.AsyncClient,
    *,
    method: str,
    path: str,
    tenant: str | None,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | list[Any] | None = None,
    access_token: str | None = None,
) -> ProbeResult:
    resolved_headers = dict(headers or {})
    if tenant:
        resolved_headers.setdefault("X-Tenant", tenant)
    if access_token:
        resolved_headers.setdefault("Authorization", f"Bearer {access_token}")
    started = time.perf_counter()
    response = await client.request(
        method=method.upper(),
        url=path,
        headers=resolved_headers,
        json=json_body,
    )
    elapsed = (time.perf_counter() - started) * 1000
    return ProbeResult(status_code=response.status_code, latency_ms=elapsed)


async def _resolve_access_token(
    client: httpx.AsyncClient,
    *,
    login_url: str,
    email: str,
    password: str,
    tenant: str | None,
) -> str:
    """One-shot login at probe start; returns ``access_token`` for the load loop.

    Issues a single POST to ``login_url`` with ``X-Tenant`` resolution mirroring
    :func:`_hit`. The login response is the FastAPI ``TokenPair`` shape
    (``{"access_token": ...}``) — refresh token lives in an HttpOnly cookie that
    perf scenarios don't exercise.

    Raised RuntimeError surfaces the HTTP body to make CI diagnostics quick: a
    401 here usually means the bootstrap admin wasn't seeded (``ADMIN_BOOTSTRAP``
    or ``ADMIN_PASSWORD`` missing) or ``app_env`` is not in ``{development,test}``.
    """

    headers: dict[str, str] = {}
    if tenant:
        headers["X-Tenant"] = tenant
    response = await client.post(
        login_url,
        headers=headers,
        json={"email": email, "password": password},
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Auth login {login_url} failed: status={response.status_code} body={response.text[:200]}"
        )
    payload = response.json()
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not token:
        raise RuntimeError(f"Auth login {login_url} returned no access_token: {payload!r}")
    return str(token)


async def _hit_flow(
    client: httpx.AsyncClient,
    *,
    tenant: str | None,
    flow_steps: list[dict[str, Any]],
    worker_idx: int,
    access_token: str | None = None,
) -> ProbeResult:
    started = time.perf_counter()
    context: dict[str, Any] = {
        "worker_idx": worker_idx,
        "run_uuid": uuid.uuid4().hex,
    }
    status_code = 200

    for step_idx, step in enumerate(flow_steps):
        step_context = {
            **context,
            "step_idx": step_idx,
            "idempotency_key": f"perf-{worker_idx}-{step_idx}-{context['run_uuid']}",
        }
        method = str(step.get("method", "GET")).upper()
        path = _render_template(step["path"], step_context)
        headers = _render_template(step.get("headers", {}), step_context)
        body = _render_template(step.get("body"), step_context)
        expected_status = int(step.get("expect_status", 200))

        resolved_headers = dict(headers or {})
        if tenant:
            resolved_headers.setdefault("X-Tenant", tenant)
        if access_token:
            resolved_headers.setdefault("Authorization", f"Bearer {access_token}")

        response = await client.request(method=method, url=path, headers=resolved_headers, json=body)
        status_code = response.status_code
        if response.status_code != expected_status:
            break

        capture = step.get("capture", {})
        if capture:
            payload = response.json()
            for name, json_path in capture.items():
                captured = _extract_json_path(payload, str(json_path))
                if captured is not None:
                    context[name] = captured

    elapsed = (time.perf_counter() - started) * 1000
    return ProbeResult(status_code=status_code, latency_ms=elapsed)


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
    parser.add_argument("--method", default="GET")
    parser.add_argument("--tenant", default=None)
    parser.add_argument("--headers-json", default=None)
    parser.add_argument("--body-json", default=None)
    parser.add_argument("--flow-json", default=None)
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--expect-status", type=int, default=200)
    parser.add_argument("--max-error-rate", type=float, default=None)
    parser.add_argument("--min-throughput", type=float, default=None)
    parser.add_argument("--max-p50-ms", type=float, default=None)
    parser.add_argument("--max-p95-ms", type=float, default=None)
    parser.add_argument("--max-p99-ms", type=float, default=None)
    parser.add_argument("--output-json", default=None)
    # iter-27 RB-002 perf-auth: bearer-token plumbing.
    # Two modes: (a) supply a precomputed --access-token (e.g. captured in CI
    # shell), or (b) supply --login-email / --login-password and let the script
    # log in once via --login-url before the load loop. The resolved token is
    # then injected as ``Authorization: Bearer <jwt>`` into every probe — this
    # keeps the load loop measuring the target endpoint's latency, not the
    # per-call login overhead.
    parser.add_argument("--access-token", default=None,
                        help="Precomputed JWT to send as Authorization: Bearer header.")
    parser.add_argument("--login-url", default="/api/v1/auth/login",
                        help="POST endpoint that exchanges email/password for access_token.")
    parser.add_argument("--login-email", default=None,
                        help="Login email used to obtain --access-token (mutually exclusive).")
    parser.add_argument("--login-password", default=None,
                        help="Login password matching --login-email.")
    args = parser.parse_args()

    if args.access_token and (args.login_email or args.login_password):
        parser.error("--access-token is mutually exclusive with --login-email/--login-password")
    if bool(args.login_email) != bool(args.login_password):
        parser.error("--login-email and --login-password must be provided together")

    limits = httpx.Limits(
        max_connections=args.concurrency, max_keepalive_connections=args.concurrency
    )
    timeout = httpx.Timeout(15.0)
    results: list[ProbeResult] = []
    errors: list[str] = []
    sem = asyncio.Semaphore(args.concurrency)

    started = time.perf_counter()
    async with httpx.AsyncClient(base_url=args.base_url, limits=limits, timeout=timeout) as client:
        headers_payload: dict[str, str] | None = None
        body_payload: dict[str, Any] | list[Any] | None = None
        flow_steps: list[dict[str, Any]] | None = None
        if args.headers_json:
            headers_payload = json.loads(args.headers_json)
        if args.body_json:
            body_payload = json.loads(args.body_json)
        if args.flow_json:
            flow_steps = json.loads(args.flow_json)

        # Resolve auth token BEFORE the load loop starts so all worker tasks
        # share a single JWT. CLI validation above guarantees the modes are
        # mutually exclusive.
        access_token: str | None = args.access_token
        if args.login_email and args.login_password:
            access_token = await _resolve_access_token(
                client,
                login_url=args.login_url,
                email=args.login_email,
                password=args.login_password,
                tenant=args.tenant,
            )

        async def worker() -> None:
            async with sem:
                try:
                    if flow_steps:
                        idx = len(results) + len(errors)
                        results.append(
                            await _hit_flow(
                                client,
                                tenant=args.tenant,
                                flow_steps=flow_steps,
                                worker_idx=idx,
                                access_token=access_token,
                            )
                        )
                    else:
                        results.append(
                            await _hit(
                                client,
                                method=args.method,
                                path=args.path,
                                tenant=args.tenant,
                                headers=headers_payload,
                                json_body=body_payload,
                                access_token=access_token,
                            )
                        )
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
