"""SEC-65 acceptance: the runtime role guard against a REAL PostgreSQL cluster.

``test_rls_runtime_role_guard.py`` pins the decision logic; this module pins the
two facts that logic rests on and that no amount of unit testing can prove:

* ``scripts/provision_app_role.py`` really produces a ``NOSUPERUSER NOBYPASSRLS``
  role with enough grants to run the application;
* the guard reads Postgres correctly — it passes for that role, and it refuses to
  start under a superuser or a ``BYPASSRLS`` role, which is exactly the
  configuration that made all 264 tenant-isolation policies decorative.

Roles are cluster-global (they survive ``DROP DATABASE``), so every role created
here is dropped in ``finally``.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import uuid
from pathlib import Path

import pytest

from app.db.rls_runtime import (
    UnsafeDatabaseRoleError,
    inspect_current_role,
    verify_runtime_role_for_url,
)

ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL")
REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the runtime-role guard against PG"
    ),
]


def _load_provision_module():
    """``scripts/`` is not a package — load the CLI by path."""

    path = REPO_ROOT / "scripts" / "provision_app_role.py"
    spec = importlib.util.spec_from_file_location("provision_app_role", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _base_dsn() -> str:
    return ADMIN_URL.rsplit("/", 1)[0]


def _async_url(dbname: str, *, user: str | None = None, password: str | None = None) -> str:
    base = _base_dsn().replace("postgresql://", "", 1)
    host = base.split("@", 1)[1] if "@" in base else base
    credentials = f"{user}:{password}@" if user else base.split("@", 1)[0] + "@"
    return f"postgresql+asyncpg://{credentials}{host}/{dbname}"


async def _admin_exec(dsn: str, *statements: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        for statement in statements:
            await conn.execute(statement)
    finally:
        await conn.close()


@pytest.fixture()
def scratch_db() -> str:
    """A throwaway database; roles created inside the tests are dropped by them."""

    dbname = f"rls_role_{uuid.uuid4().hex[:12]}"
    admin_root = f"{_base_dsn()}/postgres"
    asyncio.run(_admin_exec(admin_root, f'CREATE DATABASE "{dbname}"'))
    try:
        yield dbname
    finally:
        asyncio.run(
            _admin_exec(
                admin_root,
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{dbname}' AND pid <> pg_backend_pid()",
                f'DROP DATABASE IF EXISTS "{dbname}"',
            )
        )


def _drop_role(dbname: str, role: str) -> None:
    asyncio.run(
        _admin_exec(
            f"{_base_dsn()}/{dbname}",
            f'REASSIGN OWNED BY "{role}" TO CURRENT_USER',
            f'DROP OWNED BY "{role}"',
            f'DROP ROLE IF EXISTS "{role}"',
        )
    )


def test_provisioned_role_is_unprivileged_and_passes_the_guard(scratch_db: str) -> None:
    provision = _load_provision_module()
    role = f"rls_app_{uuid.uuid4().hex[:8]}"
    password = uuid.uuid4().hex
    admin_url = f"{_base_dsn()}/{scratch_db}"

    try:
        statements = asyncio.run(provision.provision(admin_url, role, password))
        assert any("NOSUPERUSER NOBYPASSRLS" in statement for statement in statements)

        privileges = asyncio.run(
            verify_runtime_role_for_url(
                _async_url(scratch_db, user=role, password=password),
                enforce=True,  # must NOT raise: this is the whole point of the role
                component="test",
            )
        )
        assert privileges is not None
        assert privileges.role_name == role
        assert privileges.is_superuser is False
        assert privileges.bypasses_rls is False
        assert privileges.enforces_rls is True
    finally:
        _drop_role(scratch_db, role)


def test_provisioning_is_idempotent(scratch_db: str) -> None:
    provision = _load_provision_module()
    role = f"rls_app_{uuid.uuid4().hex[:8]}"
    admin_url = f"{_base_dsn()}/{scratch_db}"

    try:
        first = asyncio.run(provision.provision(admin_url, role, uuid.uuid4().hex))
        second = asyncio.run(provision.provision(admin_url, role, uuid.uuid4().hex))
        assert first[0].startswith("CREATE ROLE")
        assert second[0].startswith("ALTER ROLE")  # repairs, never duplicates
    finally:
        _drop_role(scratch_db, role)


def test_guard_repairs_a_role_that_drifted_to_privileged(scratch_db: str) -> None:
    """The realistic regression: someone grants BYPASSRLS "to debug" and forgets."""

    provision = _load_provision_module()
    role = f"rls_app_{uuid.uuid4().hex[:8]}"
    password = uuid.uuid4().hex
    admin_url = f"{_base_dsn()}/{scratch_db}"
    app_url = _async_url(scratch_db, user=role, password=password)

    try:
        asyncio.run(provision.provision(admin_url, role, password))
        asyncio.run(_admin_exec(admin_url, f'ALTER ROLE "{role}" BYPASSRLS'))

        with pytest.raises(UnsafeDatabaseRoleError) as excinfo:
            asyncio.run(verify_runtime_role_for_url(app_url, enforce=True, component="test"))
        assert "BYPASSRLS" in str(excinfo.value)

        # Re-running the provisioner is the documented fix.
        asyncio.run(provision.provision(admin_url, role, password))
        privileges = asyncio.run(
            verify_runtime_role_for_url(app_url, enforce=True, component="test")
        )
        assert privileges is not None and privileges.enforces_rls
    finally:
        _drop_role(scratch_db, role)


def test_guard_rejects_the_bootstrap_superuser(scratch_db: str) -> None:
    """The status quo this change closes: compose connects as the cluster superuser."""

    with pytest.raises(UnsafeDatabaseRoleError) as excinfo:
        asyncio.run(
            verify_runtime_role_for_url(_async_url(scratch_db), enforce=True, component="test")
        )
    assert "SUPERUSER" in str(excinfo.value)
    assert "provision_app_role.py" in str(excinfo.value)


def test_superuser_only_warns_when_enforcement_is_off(scratch_db: str) -> None:
    """Local development keeps working on the bootstrap role — loudly, but working."""

    privileges = asyncio.run(
        verify_runtime_role_for_url(_async_url(scratch_db), enforce=False, component="test")
    )
    assert privileges is not None
    assert privileges.enforces_rls is False


def test_inspect_returns_none_for_sqlite(tmp_path: Path) -> None:
    """SQLite has no row security at all — the guard must treat it as N/A, not a failure."""

    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'probe.db'}")

    async def _probe() -> None:
        async with engine.connect() as conn:
            assert await inspect_current_role(conn) is None
        await engine.dispose()

    asyncio.run(_probe())
