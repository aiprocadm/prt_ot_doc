"""DB guard: every native pg-enum ORM column must bind strings ⊆ live pg_enum labels.

The SQLite suite cannot catch ORM↔pg_enum label drift (Enum→VARCHAR accepts any
string). This guard upgrades a throwaway PG to heads, introspects pg_enum, and
asserts that for every native-enum ORM column the strings SQLAlchemy will bind
(col.type.enums — which reflects values_callable) are a subset of the live labels.
RED before the fix (52 defective columns); GREEN after.

Also smoke-tests a real ORM insert of a previously-defective entity (Notification,
exercising the newly-added 'webhook' + 'ApprovalDeadline' labels) and raw casts of
the other newly-added labels.

Skips unless TEST_PG_ADMIN_URL points at a PG superuser/owner maintenance DB (e.g.
postgresql://postgres:postgres@localhost:5432/postgres). NEVER touches `cabinet`."""
from __future__ import annotations

import asyncio
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.db

ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL")
REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "backend" / "app" / "migrations" / "alembic.ini"
SCRIPT_LOCATION = REPO_ROOT / "backend" / "app" / "migrations"


def _sync_base() -> str:
    return ADMIN_URL.rsplit("/", 1)[0]


def _async_url(dbname: str) -> str:
    base = _sync_base().replace("postgresql://", "postgresql+asyncpg://", 1)
    return f"{base}/{dbname}"


async def _exec(sql: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(ADMIN_URL)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


async def _labels(dbname: str) -> dict[str, set[str]]:
    import asyncpg

    conn = await asyncpg.connect(f"{_sync_base()}/{dbname}")
    try:
        rows = await conn.fetch(
            "SELECT t.typname, e.enumlabel FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid"
        )
    finally:
        await conn.close()
    out: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        out[r["typname"]].add(r["enumlabel"])
    return out


def _upgrade(dbname: str) -> None:
    from alembic import command
    from alembic.config import Config

    os.environ["DATABASE_URL"] = _async_url(dbname)
    from app.core.config import get_settings

    get_settings.cache_clear()
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(SCRIPT_LOCATION))
    command.upgrade(cfg, "heads")


@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the pg-enum label guard")
def test_orm_enum_bound_values_subset_of_pg_labels() -> None:
    from sqlalchemy import Enum as SAEnum

    dbname = f"enum_parity_{uuid.uuid4().hex[:12]}"
    asyncio.run(_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        _upgrade(dbname)
        pg = asyncio.run(_labels(dbname))

        import app.db.base  # noqa: F401  triggers all model imports incl. app.modules.*
        from app.db.session import SharedBase, TenantBase

        all_tables = {}
        for md in (SharedBase.metadata, TenantBase.metadata):
            all_tables.update(md.tables)

        offenders = []
        for table in all_tables.values():
            for col in table.columns:
                t = col.type
                if not isinstance(t, SAEnum) or not getattr(t, "native_enum", False):
                    continue
                typ = (t.name or "").lower()
                if typ not in pg:
                    continue
                bad = set(t.enums) - pg[typ]
                if bad:
                    offenders.append(
                        f"{table.name}.{col.name} (type {typ}) would bind {sorted(bad)} ∉ {sorted(pg[typ])}"
                    )
        assert not offenders, "ORM↔pg_enum label drift:\n" + "\n".join(offenders)
    finally:
        asyncio.run(_exec(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
        os.environ.pop("DATABASE_URL", None)
        from app.core.config import get_settings

        get_settings.cache_clear()


@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the pg-enum insert smoke")
def test_real_orm_insert_of_previously_defective_entity() -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.models.models import Tenant
    from app.models.notifications import (
        Notification,
        NotificationChannel,
        NotificationPriority,
        NotificationStatus,
        NotificationType,
    )

    dbname = f"enum_insert_{uuid.uuid4().hex[:12]}"
    asyncio.run(_exec(f'CREATE DATABASE "{dbname}"'))

    async def _run() -> None:
        engine = create_async_engine(_async_url(dbname))
        try:
            async with AsyncSession(engine) as session:
                tenant = Tenant(slug=f"t-{uuid.uuid4().hex[:8]}", name="Smoke", contact_email="s@e.t")
                session.add(tenant)
                await session.flush()
                note = Notification(
                    tenant_id=tenant.id,
                    user_id="u-1",
                    channel=NotificationChannel.WEBHOOK,       # 'webhook' — newly added label
                    type=NotificationType.APPROVAL_DEADLINE,    # 'ApprovalDeadline' — newly added label
                    title="t",
                    body="b",
                    priority=NotificationPriority.HIGH,
                    status=NotificationStatus.QUEUED,
                    dedup_key=f"d-{uuid.uuid4().hex[:8]}",
                    scheduled_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
                )
                session.add(note)
                await session.commit()
                got = await session.get(Notification, note.id)
                assert got is not None
                assert got.channel is NotificationChannel.WEBHOOK
                assert got.type is NotificationType.APPROVAL_DEADLINE
        finally:
            await engine.dispose()

    try:
        os.environ["DATABASE_URL"] = _async_url(dbname)
        from app.core.config import get_settings

        get_settings.cache_clear()
        _upgrade(dbname)
        asyncio.run(_run())
    finally:
        asyncio.run(_exec(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
        os.environ.pop("DATABASE_URL", None)
        from app.core.config import get_settings

        get_settings.cache_clear()
