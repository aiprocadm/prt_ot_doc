"""Pin tests for ``aensure_shared_schema`` async startup path.

iter-22 fixes the cascade failure observed on perf-smoke after iter-21
unblocked api-1 startup past the ``user.company_id`` schema drift:

    RuntimeError: Task <Task ... _create_tenant_schema ...> got Future
    ... attached to a different loop

Root cause: the first ``AsyncSessionLocal`` call from
``bootstrap_admin_user`` cascades into the **sync** ``ensure_shared_schema
(implicit=True)`` at ``backend/app/db/session.py:514``, which uses
``_run_in_thread`` + ``asyncio.run`` to bridge async work. That worker
thread spins up a fresh event loop, initialises the global ``engine``'s
connection pool with asyncpg connections whose futures are tied to the
worker loop, then exits. Subsequent access from the main lifespan loop
sees those stale futures and raises ``Future attached to a different
loop`` — aborting ``_create_tenant_schema`` mid-flight, leaving the
tenant schema empty, and surfacing as ``UndefinedTableError: relation
"training_course" does not exist`` when ``bootstrap_demo_tenant`` later
selects from it.

iter-22 ships:

1. New ``aensure_shared_schema`` async function (mirrors the existing
   ``aensure_tenant_schema`` pattern from iter-16f).
2. Lifespan in ``backend/app/api/app.py`` calls
   ``await aensure_shared_schema()`` BEFORE any session work — once the
   async path sets ``_shared_initialized = True``, the sync ``ensure_
   shared_schema(implicit=True)`` short-circuits and never spawns the
   worker thread.

These pin tests guard against regression in the direction that re-removes
the async wrapper or its lifespan call.
"""

from __future__ import annotations

import asyncio
import inspect

from app.db import session as session_module


def test_aensure_shared_schema_exists_as_coroutine_function() -> None:
    assert hasattr(session_module, "aensure_shared_schema"), (
        "aensure_shared_schema must exist — lifespan in backend/app/api/app.py "
        "depends on it to avoid the cross-loop asyncpg Future bug"
    )
    assert asyncio.iscoroutinefunction(session_module.aensure_shared_schema), (
        "aensure_shared_schema must be `async def` — a sync stub would re-introduce "
        "the worker-loop + asyncio.run pattern that this fix is preventing"
    )


def test_aensure_shared_schema_signature_matches_sync_counterpart() -> None:
    # Same keyword API as ensure_shared_schema (implicit flag) so callers can
    # swap by adding `await` without other changes. Drift here = harder migration.
    sync_sig = inspect.signature(session_module.ensure_shared_schema)
    async_sig = inspect.signature(session_module.aensure_shared_schema)
    assert list(sync_sig.parameters) == list(async_sig.parameters)
    assert sync_sig.parameters["implicit"].kind == async_sig.parameters["implicit"].kind


def test_lifespan_calls_aensure_shared_schema_before_bootstraps() -> None:
    # Source-level pin: text-scan the lifespan body to confirm the async
    # provisioner is awaited before bootstrap_admin_user (the first session_
    # scope consumer). A future refactor that reorders these calls would
    # silently re-introduce the bug. Cheap text check beats spinning up the
    # full app.
    from pathlib import Path  # noqa: PLC0415

    app_module_path = Path(session_module.__file__).resolve().parents[1] / "api" / "app.py"
    source = app_module_path.read_text(encoding="utf-8")

    aensure_idx = source.find("await aensure_shared_schema(")
    admin_idx = source.find("await bootstrap_admin_user(")
    demo_idx = source.find("await bootstrap_demo_tenant(")

    assert aensure_idx != -1, "lifespan must call aensure_shared_schema (iter-22 fix)"
    assert admin_idx != -1, "lifespan must call bootstrap_admin_user"
    assert demo_idx != -1, "lifespan must call bootstrap_demo_tenant"
    assert aensure_idx < admin_idx, (
        "aensure_shared_schema must precede bootstrap_admin_user — otherwise the "
        "implicit sync ensure_shared_schema cascade from AsyncSessionLocal "
        "re-introduces the cross-loop pool corruption"
    )
    assert aensure_idx < demo_idx
