from __future__ import annotations

import asyncio
import os
import sys
import threading
import types
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings


def prepare_runtime(settings: Settings) -> Settings:
    """Normalize local runtime defaults before the app is created."""

    sys.modules.setdefault("crypt", types.SimpleNamespace(crypt=lambda secret, salt: "mocked"))

    if settings.database_url.startswith("sqlite+aiosqlite"):
        _prepare_sqlite_metadata()
        _run_coro_sync(_initialize_sqlite(settings.database_url))

        # Dockerless SQLite: skip demo seeding by default, but honor DEMO_BOOTSTRAP=1 (README / run_backend_lite).
        if settings.app_run_mode == "dockerless":
            env_on = os.environ.get("DEMO_BOOTSTRAP", "").strip().lower() in {"1", "true", "yes"}
            if not env_on:
                settings.demo_bootstrap = False

    return settings


def _run_coro_sync(coro) -> None:
    """Синхронный запуск async: только для prepare_runtime / SQLite init (не hot path).

    Параллельный bridge для Celery см. :func:`app.tasks._core._run_coroutine` (daemon thread + ``asyncio.run``).
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return

    error: list[BaseException] = []

    def _runner() -> None:
        try:
            asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - defensive bridge
            error.append(exc)

    thread = threading.Thread(target=_runner, daemon=False)
    thread.start()
    thread.join()
    if error:
        raise error[0]


def _prepare_sqlite_metadata() -> None:
    from app.db import Base, SharedBase
    from app.models.models import Tenant

    # Register module models used outside app.models.models so sqlite create_all
    # includes contractor registry tables in dockerless mode.
    from app.modules.contractors import models as _contractors_models  # noqa: F401

    SharedBase.metadata.schema = None
    for table in SharedBase.metadata.tables.values():
        table.schema = None
    if "tenant" not in Base.metadata.tables:
        Tenant.__table__.to_metadata(Base.metadata, schema=None)


async def _initialize_sqlite(database_url: str) -> None:
    from app.db import Base, SharedBase
    from app.db.session import configure_engine

    db_path = database_url.removeprefix("sqlite+aiosqlite:///")
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    configure_engine(database_url=database_url, echo=False)
    engine = create_async_engine(database_url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SharedBase.metadata.create_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
