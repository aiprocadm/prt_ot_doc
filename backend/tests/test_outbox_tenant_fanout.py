"""SEC-65: the outbox drain must cover every tenant, not one hard-coded slug.

Both outbox dispatchers are tenant-scoped — they carry no ``tenant_id`` predicate
and rely on the session's tenant context (and, on PostgreSQL, on the row-level
policies). Before ``outbox.dispatch_all`` nothing enqueued them for more than a
single tenant, and ``dispatch_outbox_events`` even defaulted to the slug
``"test"``, so an unqualified call quietly worked on whichever tenant owns that
slug — and under FORCE row-level security it would now see nothing at all.
"""

from __future__ import annotations

import inspect

import pytest

from app.tasks import _core


@pytest.fixture()
def fanout(monkeypatch: pytest.MonkeyPatch):
    """Replace every I/O boundary of the fan-out with recorders.

    The recorders capture the tenant the fan-out had entered at the moment of each
    call, which is what the loop must get right.
    """

    state = {
        "slugs": ["alpha", "beta", "gamma"],
        "entered": None,
        "processed": [],
        "events": [],
        "schemas": [],
        "fail_for": set(),
    }

    class _TenantContext:
        def __init__(self, slug: str) -> None:
            self.slug = slug

        def __enter__(self):
            state["entered"] = self.slug
            return self

        def __exit__(self, *exc) -> bool:
            return False

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> bool:
            return False

    class _Processor:
        def __init__(self, session) -> None:  # noqa: ANN001 - test double
            self.session = session

        async def process_once(self) -> int:
            slug = state["entered"]
            state["processed"].append(slug)
            if slug in state["fail_for"]:
                raise RuntimeError(f"outbox exploded for {slug}")
            return 1

    async def _events(*, max_attempts, tenant_slug):  # noqa: ANN001 - test double
        state["events"].append(tenant_slug)
        return 10

    monkeypatch.setattr(_core, "_active_tenant_slugs", lambda: _as_coro(state["slugs"]))
    monkeypatch.setattr(_core, "tenant_context", _TenantContext)
    monkeypatch.setattr(_core, "ensure_tenant_schema", state["schemas"].append)
    monkeypatch.setattr(_core, "session_scope", lambda **kwargs: _Session())
    monkeypatch.setattr(_core, "OutboxProcessor", _Processor)
    monkeypatch.setattr(_core, "_dispatch_outbox_events", _events)
    return state


async def _as_coro(value):
    return value


def test_fanout_covers_every_active_tenant(fanout) -> None:
    result = _core.dispatch_outbox_all()

    assert fanout["processed"] == fanout["slugs"]
    assert fanout["events"] == fanout["slugs"]
    assert fanout["schemas"] == fanout["slugs"], "each tenant schema must be ensured"
    assert result == {
        "tenants": 3,
        "outbox": 3,  # 1 per tenant
        "outbox_events": 30,  # 10 per tenant
        "failed_tenants": 0,
    }


def test_one_failing_tenant_does_not_strand_the_others(fanout) -> None:
    """A single tenant's error must not leave the rest of the fleet undrained."""

    fanout["fail_for"] = {"beta"}

    result = _core.dispatch_outbox_all()

    assert fanout["processed"] == ["alpha", "beta", "gamma"], "loop stopped early"
    assert result["failed_tenants"] == 1
    assert result["tenants"] == 3
    # beta raised before reaching its events dispatch; alpha and gamma completed
    assert fanout["events"] == ["alpha", "gamma"]
    assert result["outbox"] == 2
    assert result["outbox_events"] == 20


def test_dispatch_outbox_events_requires_an_explicit_tenant() -> None:
    """The old ``tenant_slug="test"`` default made a fleet-wide call silently wrong."""

    tenant_param = inspect.signature(_core.dispatch_outbox_events).parameters["tenant_slug"]
    assert tenant_param.default is inspect.Parameter.empty


def test_beat_schedule_is_opt_in() -> None:
    """Enabling the drain flushes any accumulated backlog, so it must be deliberate."""

    from app.core.config import get_settings
    from app.services.celery_app import celery_app

    settings = get_settings()
    scheduled = "outbox-dispatch-all" in celery_app.conf.beat_schedule
    assert scheduled == settings.outbox_dispatch_schedule_enabled
    assert settings.outbox_dispatch_schedule_enabled is False, "default must stay OFF"
