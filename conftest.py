"""Root conftest — session-wide test environment setup before any collection.

``tests/conftest.py`` performs the pre-import environment setup (test DB, memory
Redis, non-blank secrets, Windows event-loop policy), but a conftest applies only
to its own subtree. ``backend/tests`` and ``integration_tests`` have no conftest,
so modules there that import the app at module load (e.g.
``backend/tests/test_health_checks.py`` -> ``from app.main import app``) ran with
the *real* ``.env`` instead: blank ``SECRET_KEY=`` failed ``bootstrap("api")``,
and ``DATABASE_URL=...///./dev.db`` made ``prepare_runtime`` run ``create_all``
against the persistent dev database (drifted schema -> "index ... already exists").

Hoisting the setup here (rootdir conftest is imported by pytest in every worker
before any test is collected) gives all testpaths the same safe test env. Values
mirror ``tests/conftest.py``; every assignment is ``setdefault`` / ``_ensure_nonblank``
(idempotent), so an explicit env var or ``tests/conftest.py`` re-running it is a
no-op. Pytest-only — never imported by the running app, so production is unaffected.
"""

from __future__ import annotations

import os
import sys
import tempfile
import types

# Environment must be set BEFORE app imports (which read settings at import time).
os.environ.setdefault("APP_NAME", "TestService")
os.environ["APP_TRUSTED_HOSTS"] = "localhost,127.0.0.1,testserver"
os.environ.setdefault("DEFAULT_LOCALE", "en-US")
os.environ.setdefault("LIBREOFFICE_BIN", sys.executable)
os.environ["ENABLE_METRICS"] = "true"

# app.main import runs prepare_runtime → _initialize_sqlite(create_all) at import time.
# Under xdist every worker would create_all the SAME file concurrently ("table ...
# already exists" / database locked), so give each worker its own DB file. Workers
# inherit the controller's DATABASE_URL via the environment, so a worker must OVERRIDE
# it (setdefault would keep the shared inherited value).
_xdist_worker = os.environ.get("PYTEST_XDIST_WORKER", "")
_db_name = f"prt_ot_doc_tests_{_xdist_worker}.db" if _xdist_worker else "prt_ot_doc_tests.db"
_DEFAULT_SQLITE_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), _db_name)
if _xdist_worker:
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DEFAULT_SQLITE_TEST_DB_PATH}"
else:
    os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_DEFAULT_SQLITE_TEST_DB_PATH}")
# Local file storage is a shared on-disk dir that the _reset_storage autouse fixture
# wipes via shutil.rmtree between tests. Under xdist a shared root lets one worker's
# clear() delete another worker's files mid-test (empty reads / 500s on read-back).
# Give each worker its own storage root, mirroring the per-worker DATABASE_URL above.
if _xdist_worker:
    os.environ["STORAGE_ROOT"] = os.path.join(
        tempfile.gettempdir(), f"prt_ot_storage_{_xdist_worker}"
    )
else:
    os.environ.setdefault("STORAGE_ROOT", "./.local_storage")
os.environ.setdefault("REDIS_URL", "memory://")
os.environ.setdefault("REDIS_RESULT_URL", "cache+memory://")
os.environ.setdefault("RATE_LIMIT_STORAGE_URI", "memory://")
os.environ.setdefault("S3_ENDPOINT", "http://localhost")


def _ensure_nonblank(name: str, value: str) -> None:
    """Set ``name`` to ``value`` only when absent or blank (bootstrap() rejects blanks)."""

    if not str(os.environ.get(name, "")).strip():
        os.environ[name] = value


# A bare ``SECRET_KEY=`` in .env overrides the Pydantic default with "" and breaks
# bootstrap("api"); normalize the keys bootstrap requires non-blank.
_ensure_nonblank("SECRET_KEY", "test-secret-key-not-for-production")
_ensure_nonblank("S3_ACCESS_KEY", "prt_local_access")
_ensure_nonblank("S3_SECRET_KEY", "prt_local_secret")
_ensure_nonblank("S3_BUCKET", "documents")

# Some environments (Windows, slim containers) lack the stdlib ``crypt`` module that
# passlib imports during auth setup; provide a tiny stub before app import.
sys.modules.setdefault("crypt", types.SimpleNamespace(crypt=lambda secret, salt: "mocked"))

# Windows: aiosqlite's worker thread can deadlock under the default Proactor loop in
# sync-wrapped-async paths (e.g. prepare_runtime's asyncio.run(_initialize_sqlite)).
# The Selector loop avoids it; no effect on Linux/CI. Must run before any loop is created.
import asyncio as _asyncio  # noqa: E402

if sys.platform == "win32":
    try:
        _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:  # pragma: no cover - non-Windows / older runtimes
        pass


# Test-only SQLite speedup. The per-test ``app_fixture`` runs ``create_all`` over
# 100+ tables and seeds tenants on a fresh on-disk SQLite file every test; default
# ``synchronous=FULL`` fsyncs each DDL/INSERT, dominating wall-clock (single
# create_all measured at ~11-14s). ``synchronous=OFF`` + in-memory journal removes
# the fsyncs. This changes only crash-durability, never SQL results, so it cannot
# alter any test's pass/fail outcome — purely a speed lever for the test process.
from sqlalchemy import event as _sa_event  # noqa: E402
from sqlalchemy.engine import Engine as _SAEngine  # noqa: E402


@_sa_event.listens_for(_SAEngine, "connect")
def _sqlite_test_speed_pragmas(dbapi_connection, connection_record):  # noqa: ANN001
    # SQLite-only. This listener is attached to the base ``Engine`` class, so it
    # ALSO fires for Postgres connections — e.g. the @pytest.mark.db PG guards
    # (alembic upgrade/downgrade, enum label-drift). On Postgres ``PRAGMA`` is a
    # syntax error that aborts the connection's transaction; the ``except`` below
    # swallows the *Python* exception but the server-side transaction stays
    # aborted, so the very next statement (asyncpg JSON-codec introspection or the
    # first migration) dies with ``InFailedSQLTransactionError``. Guard strictly
    # to SQLite drivers — both ``sqlite3`` (sync) and ``aiosqlite`` (async) carry
    # "sqlite" in their module path; asyncpg / psycopg2 do not.
    if "sqlite" not in type(dbapi_connection).__module__:
        return
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA synchronous=OFF")
        cursor.execute("PRAGMA journal_mode=MEMORY")
        cursor.close()
    except Exception:  # pragma: no cover - non-SQLite drivers / unsupported conns
        pass
