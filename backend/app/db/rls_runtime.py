"""SEC-65: runtime guard for the database role the application connects with.

Postgres row-level security is *not applied* to a role that is ``SUPERUSER`` or
that carries ``BYPASSRLS`` — not even on a table declared ``FORCE ROW LEVEL
SECURITY``. The 264 tenant-isolation policies rolled out in Phase 16 are
therefore decorative whenever the runtime connects as such a role, which is what
the stock ``docker-compose.yml`` used to do (``POSTGRES_USER`` is the cluster
bootstrap superuser).

Closing SEC-65 requires two halves:

* provisioning — the application/Celery role must be ``NOSUPERUSER NOBYPASSRLS``
  (see ``scripts/provision_app_role.py`` and ``infra/postgres/initdb``), while
  Alembic keeps running as the owner role via ``MIGRATION_DATABASE_URL``;
* verification — this module, wired into the API lifespan, the Celery worker
  bootstrap and CI, so a misprovisioned deployment fails loudly instead of
  silently serving cross-tenant data.

Role attributes in Postgres are never inherited through membership: only the
attributes on ``current_user``'s own ``pg_roles`` row decide whether row
security applies. Membership in a privileged role is still reported, because
such a role can reach the attributes with an explicit ``SET ROLE``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
from sqlalchemy.pool import NullPool

_logger = logging.getLogger(__name__)

# Own attributes decide enforcement; membership only enables `SET ROLE`.
_ROLE_PRIVILEGE_SQL = text(
    """
    SELECT
        current_user AS role_name,
        me.rolsuper AS is_superuser,
        me.rolbypassrls AS bypasses_rls,
        EXISTS (
            SELECT 1
            FROM pg_roles other
            WHERE (other.rolsuper OR other.rolbypassrls)
              AND other.rolname <> current_user
              AND pg_has_role(current_user, other.oid, 'MEMBER')
        ) AS can_escalate
    FROM pg_roles me
    WHERE me.rolname = current_user
    """
)


class UnsafeDatabaseRoleError(RuntimeError):
    """Raised when the runtime role would bypass row-level security."""


@dataclass(frozen=True)
class DatabaseRolePrivileges:
    """Privileges of the role the current connection authenticated as."""

    role_name: str
    is_superuser: bool
    bypasses_rls: bool
    can_escalate: bool = False

    @property
    def enforces_rls(self) -> bool:
        """True when Postgres will actually apply row-level policies to this role."""

        return not self.is_superuser and not self.bypasses_rls

    def describe(self) -> str:
        reasons = []
        if self.is_superuser:
            reasons.append("SUPERUSER")
        if self.bypasses_rls:
            reasons.append("BYPASSRLS")
        if not reasons:
            return f"role {self.role_name!r} is NOSUPERUSER NOBYPASSRLS"
        return f"role {self.role_name!r} has {' + '.join(reasons)}"


async def inspect_current_role(
    connectable: AsyncConnection | AsyncSession,
) -> DatabaseRolePrivileges | None:
    """Return the runtime role privileges, or ``None`` when not on Postgres.

    SQLite (dev/test default) has no row security at all, so there is nothing to
    verify and the caller should treat ``None`` as "not applicable".
    """

    bind = connectable.bind if isinstance(connectable, AsyncSession) else connectable
    dialect = getattr(getattr(bind, "dialect", None), "name", None)
    if dialect != "postgresql":
        return None

    row = (await connectable.execute(_ROLE_PRIVILEGE_SQL)).first()
    if row is None:  # pragma: no cover - current_user always has a pg_roles row
        return None
    return DatabaseRolePrivileges(
        role_name=str(row.role_name),
        is_superuser=bool(row.is_superuser),
        bypasses_rls=bool(row.bypasses_rls),
        can_escalate=bool(row.can_escalate),
    )


def assert_role_enforces_rls(
    privileges: DatabaseRolePrivileges | None,
    *,
    enforce: bool,
    component: str = "app",
) -> None:
    """Fail (or warn) when the runtime role would bypass row-level security.

    ``enforce=False`` keeps local development on the bootstrap superuser usable
    while still printing a loud warning; staging/production default to
    ``enforce=True`` so a misprovisioned deployment refuses to start.
    """

    if privileges is None:
        return

    if privileges.enforces_rls:
        if privileges.can_escalate:
            _logger.warning(
                "rls.runtime_role.escalation_possible",
                extra={"component": component, "role": privileges.role_name},
            )
        _logger.info(
            "rls.runtime_role.ok",
            extra={"component": component, "role": privileges.role_name},
        )
        return

    message = (
        f"SEC-65: {privileges.describe()}, so Postgres ignores row-level security "
        "and every tenant-isolation policy is inert. Provision an application role "
        "with NOSUPERUSER NOBYPASSRLS (scripts/provision_app_role.py) and point "
        "DATABASE_URL at it; keep the owner role for MIGRATION_DATABASE_URL."
    )
    if enforce:
        raise UnsafeDatabaseRoleError(message)
    _logger.warning(
        "rls.runtime_role.unsafe",
        extra={
            "component": component,
            "role": privileges.role_name,
            "is_superuser": privileges.is_superuser,
            "bypasses_rls": privileges.bypasses_rls,
            "detail": message,
        },
    )


async def verify_runtime_role(
    connectable: AsyncConnection | AsyncSession,
    *,
    enforce: bool,
    component: str = "app",
) -> DatabaseRolePrivileges | None:
    """Inspect and validate the runtime role in one call."""

    privileges = await inspect_current_role(connectable)
    assert_role_enforces_rls(privileges, enforce=enforce, component=component)
    return privileges


async def verify_runtime_role_for_url(
    database_url: str,
    *,
    enforce: bool,
    component: str,
) -> DatabaseRolePrivileges | None:
    """Probe ``database_url`` on a throwaway engine, then dispose it.

    Callers outside the API event loop (Celery ``worker_ready``, CI scripts) must
    not touch the shared engine: seeding its pool from a short-lived
    ``asyncio.run`` loop leaves connections bound to a loop that is already gone
    ("Future attached to a different loop" on the next use).
    """

    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415

    probe_engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with probe_engine.connect() as conn:
            return await verify_runtime_role(conn, enforce=enforce, component=component)
    finally:
        await probe_engine.dispose()
