"""Срез-170: обход сроков и таймеров согласований идёт по ВСЕМ арендаторам.

Обе работы (пометить просроченные задачи согласования, исполнить созревшие
таймеры процесса) принимают арендатора параметром, поэтому в расписание они не
попадали и не запускались никогда. Веерная задача ``workflow.sweep.tick``
обходит активных арендаторов сама.

Здесь проверяется то, ради чего она написана: зайти к каждому арендатору, у
каждого выполнить обе работы и не дать сбою одного лишить обхода остальных.
Все границы ввода-вывода подменены записывающими двойниками — как в соседнем
тесте веерного слива ленты.
"""

from __future__ import annotations

import pytest

from app.tasks import _core


@pytest.fixture()
def fanout(monkeypatch: pytest.MonkeyPatch):
    state: dict[str, object] = {
        "slugs": ["alpha", "beta", "gamma"],
        "entered": None,
        "sla_for": [],
        "timers_for": [],
        "committed": [],
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

        async def commit(self) -> None:
            state["committed"].append(state["entered"])

    class _Service:
        def __init__(self, session, tenant_id: str) -> None:  # noqa: ANN001 - двойник
            self.tenant_id = tenant_id

        async def sweep_task_sla(self) -> int:
            slug = state["entered"]
            if slug in state["fail_for"]:
                raise RuntimeError(f"сбой у {slug}")
            state["sla_for"].append(slug)
            return 2

        async def run_due_timers(self) -> int:
            state["timers_for"].append(state["entered"])
            return 1

    async def _slugs() -> list[str]:
        return list(state["slugs"])

    async def _scope(session, slug: str):  # noqa: ANN001 - двойник
        return f"id-{slug}", (f"id-{slug}", slug)

    monkeypatch.setattr(_core, "_active_tenant_slugs", _slugs)
    monkeypatch.setattr(_core, "tenant_context", _TenantContext)
    monkeypatch.setattr(_core, "ensure_tenant_schema", lambda slug: None)
    monkeypatch.setattr(_core, "session_scope", lambda **kwargs: _Session())
    monkeypatch.setattr(_core, "_resolve_task_tenant_scope", _scope)

    import app.modules.workflow.service as workflow_service

    monkeypatch.setattr(workflow_service, "WorkflowService", _Service)
    return state


def test_обход_заходит_к_каждому_арендатору(fanout) -> None:
    totals = _core.workflow_sweep_tick()

    assert fanout["sla_for"] == ["alpha", "beta", "gamma"]
    assert fanout["timers_for"] == ["alpha", "beta", "gamma"]
    assert totals["tenants"] == 3
    assert totals["sla"] == 6
    assert totals["timers"] == 3
    assert totals["failed_tenants"] == 0


def test_сбой_у_одного_не_лишает_обхода_остальных(fanout) -> None:
    fanout["fail_for"] = {"beta"}

    totals = _core.workflow_sweep_tick()

    assert fanout["sla_for"] == ["alpha", "gamma"]
    assert totals["failed_tenants"] == 1
    assert totals["tenants"] == 3
    # Работа у исправных арендаторов сохранена, а не откачена вместе со сбоем.
    assert fanout["committed"] == ["alpha", "gamma"]
