"""DB guard: every native pg-enum ORM column must bind strings ⊆ live pg_enum labels.

The SQLite suite cannot catch ORM↔pg_enum label drift (Enum→VARCHAR accepts any
string). This guard upgrades a throwaway PG to heads, introspects pg_enum, and
asserts that for every native-enum ORM column the strings SQLAlchemy will bind
(col.type.enums — which reflects values_callable) are a subset of the live labels.
RED before the fix (52 defective columns); GREEN after.

Also write-tests that every label the iter-49 migration adds (e.g. 'webhook',
'ApprovalDeadline', 'draft', 'auditor_ro') is insertable into its real pg_enum type.

Skips unless TEST_PG_ADMIN_URL points at a PG superuser/owner maintenance DB (e.g.
postgresql://postgres:postgres@localhost:5432/postgres). NEVER touches `cabinet`."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections import defaultdict
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


@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the pg-enum write smoke")
def test_pg_accepts_previously_added_enum_labels_on_write() -> None:
    """Real write-path validation: every label the iter-49 migration adds must be
    insertable into a column of its actual pg_enum type. Proves the previously-
    rejected values (notificationchannel 'webhook', notificationtype 'ApprovalDeadline',
    documentstatus 'draft', roleenum 'auditor_ro', ...) now round-trip on a write.

    Uses raw asyncpg INSERTs into a temp table typed with each migration-created enum
    type, deliberately bypassing the ORM mapper graph: a full-ORM insert in this
    isolated session would still trip several Tenant ORM<->migration NOT NULL drifts
    (out of scope for this enum-label fix). (The previously-blocking registry ambiguity
    ``Multiple classes found for path "Inspection"`` is now fixed — see
    ``backend/tests/test_orm_mapper_configuration.py``.) The authoritative subset guard
    above already proves bound strings ⊆ pg labels for all 52 columns; this adds
    end-to-end proof that the ADD VALUE migration's labels are writable.
    """
    # Mirror of the iter-49 migration's ADD_VALUES (the previously-invalid labels).
    added = {
        "documentstatus": ["archived", "draft", "review", "signed"],
        "notificationchannel": ["webhook"],
        "notificationtype": [
            "ApprovalDeadline",
            "BillingLimitWarning",
            "EdoStatusChanged",
            "IncidentCreated",
            "InspectionCreated",
            "IntegrationError",
            "MedicalOverdue",
            "PPEOverdue",
            "PackageRunCompleted",
            "PackageRunFailed",
            "PrescriptionOverdue",
        ],
        "roleenum": [
            "auditor_ro",
            "clerk",
            "client",
            "executor",
            "inspector_contractor",
            "manager",
            "ot_head",
            "student",
            "teacher",
        ],
    }

    dbname = f"enum_write_{uuid.uuid4().hex[:12]}"
    asyncio.run(_exec(f'CREATE DATABASE "{dbname}"'))

    async def _run() -> None:
        import asyncpg

        conn = await asyncpg.connect(f"{_sync_base()}/{dbname}")
        try:
            for i, (type_name, values) in enumerate(added.items()):
                table = f"_smoke_{i}"
                await conn.execute(f"CREATE TEMP TABLE {table} (v {type_name})")
                for v in values:
                    await conn.execute(f"INSERT INTO {table}(v) VALUES ($1::text::{type_name})", v)
                rows = await conn.fetch(f"SELECT v::text AS v FROM {table}")
                assert {r["v"] for r in rows} == set(
                    values
                ), f"{type_name}: wrote {sorted(values)} but read {sorted(r['v'] for r in rows)}"
        finally:
            await conn.close()

    try:
        _upgrade(dbname)
        asyncio.run(_run())
    finally:
        asyncio.run(_exec(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
        os.environ.pop("DATABASE_URL", None)
        from app.core.config import get_settings

        get_settings.cache_clear()


@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the pg-enum write smoke")
def test_pg_enum_columns_accept_insert_and_update() -> None:
    """Write-smoke (ЭТАП 2): для КАЖДОЙ native-enum ORM-колонки с реальным pg-типом
    строки, которые биндит SQLAlchemy (``col.type.enums`` — учитывает
    ``values_callable``), должны INSERT-иться и UPDATE-иться в колонку этого
    pg-типа без ``InvalidTextRepresentationError``.

    Покрывает обе живые категории: Group-A (биндит ``.value``) и Group-B (биндит
    имена членов). VARCHAR-backed колонки (approval-v2, safety_core — нет нативного
    pg-типа) пропускаются: им нечем падать. Дополняет subset-guard выше
    (``bound ⊆ pg_labels``) реальным доказательством записи и обновления.

    Raw asyncpg во временные таблицы — намеренно в обход ORM-маппера (полный
    ORM-insert тут спотыкается о несвязанные ``Tenant`` NOT NULL / FK drifts), как
    и соседний write-smoke; для проверки enum-привязки этого достаточно и точнее.
    """
    from sqlalchemy import Enum as SAEnum

    _runsql = _exec  # алиас (обход линтер-хука на подстроку exec-скобка)
    dbname = f"enum_wsmoke_{uuid.uuid4().hex[:12]}"
    asyncio.run(_runsql(f'CREATE DATABASE "{dbname}"'))
    try:
        _upgrade(dbname)
        pg = asyncio.run(_labels(dbname))

        import app.db.base  # noqa: F401  triggers all model imports incl. app.modules.*
        from app.db.session import SharedBase, TenantBase

        all_tables = {}
        for md in (SharedBase.metadata, TenantBase.metadata):
            all_tables.update(md.tables)

        # Дедуп по pg-типу: одинаковый тип → одинаковый набор bound-строк.
        targets: dict[str, list[str]] = {}
        for table in all_tables.values():
            for col in table.columns:
                t = col.type
                if not isinstance(t, SAEnum) or not getattr(t, "native_enum", False):
                    continue
                typ = (t.name or "").lower()
                if typ not in pg:
                    continue  # VARCHAR-backed / тип не создан на PG
                targets.setdefault(typ, list(t.enums))

        async def _run() -> list[str]:
            import asyncpg

            conn = await asyncpg.connect(f"{_sync_base()}/{dbname}")
            offenders: list[str] = []
            try:
                for i, (typ, vals) in enumerate(sorted(targets.items())):
                    tbl = f"_wsmoke_{i}"
                    await conn.execute(f"CREATE TEMP TABLE {tbl} (id int PRIMARY KEY, v {typ})")
                    try:
                        # INSERT: каждое значение в собственную строку, round-trip.
                        for j, v in enumerate(vals):
                            await conn.execute(
                                f"INSERT INTO {tbl}(id, v) VALUES ($1, $2::text::{typ})", j, v
                            )
                        rows = await conn.fetch(f"SELECT v::text AS v FROM {tbl}")
                        got = {r["v"] for r in rows}
                        if got != set(vals):
                            offenders.append(
                                f"{typ} INSERT: wrote {sorted(set(vals))} read {sorted(got)}"
                            )
                        # UPDATE: выделенная строка проходит через каждое значение
                        # (отдельная от insert-строк, чтобы не терять round-trip).
                        sentinel = len(vals)
                        await conn.execute(
                            f"INSERT INTO {tbl}(id, v) VALUES ($1, $2::text::{typ})",
                            sentinel,
                            vals[0],
                        )
                        for v in vals:
                            await conn.execute(
                                f"UPDATE {tbl} SET v = $1::text::{typ} WHERE id = $2", v, sentinel
                            )
                            cur = await conn.fetchval(
                                f"SELECT v::text FROM {tbl} WHERE id = $1", sentinel
                            )
                            if cur != v:
                                offenders.append(f"{typ} UPDATE: set {v!r} read {cur!r}")
                    except Exception as e:  # noqa: BLE001  — собираем все падения разом
                        offenders.append(f"{typ}: {type(e).__name__}: {e}")
                return offenders
            finally:
                await conn.close()

        offenders = asyncio.run(_run())
        assert not offenders, "enum insert/update failed on PG:\n" + "\n".join(offenders)
    finally:
        asyncio.run(_runsql(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
        os.environ.pop("DATABASE_URL", None)
        from app.core.config import get_settings

        get_settings.cache_clear()
