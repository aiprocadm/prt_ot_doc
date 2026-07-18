"""Contract tests for app.tasks._run_coroutine (async/sync bridge).

Refactors must preserve: (1) sync call without running loop uses asyncio.run;
(2) call from async context completes via helper thread; (3) exceptions propagate.
"""

from __future__ import annotations

import asyncio

import pytest

from app.tasks import _run_coroutine


def test_run_coroutine_without_running_loop() -> None:
    async def work() -> int:
        return 42

    assert _run_coroutine(work()) == 42


def test_run_coroutine_without_loop_propagates_exception() -> None:
    async def bad() -> None:
        raise ValueError("expected")

    with pytest.raises(ValueError, match="expected"):
        _run_coroutine(bad())


def test_run_coroutine_with_running_loop_uses_thread_path() -> None:
    async def inner() -> str:
        async def work() -> str:
            return "thread-path"

        return _run_coroutine(work())

    assert asyncio.run(inner()) == "thread-path"


def test_run_coroutine_with_running_loop_propagates_exception() -> None:
    async def inner() -> None:
        async def bad() -> None:
            raise RuntimeError("from-thread")

        _run_coroutine(bad())

    with pytest.raises(RuntimeError, match="from-thread"):
        asyncio.run(inner())
