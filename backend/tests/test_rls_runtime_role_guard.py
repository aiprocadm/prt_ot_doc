"""SEC-65: the runtime-role guard itself (no database required).

Row-level security is skipped for ``SUPERUSER``/``BYPASSRLS`` roles, so a
deployment can carry all 264 tenant-isolation policies and still leak. These
tests pin the decision logic and the configuration that drives it; the live
Postgres behaviour is covered by ``test_rls_runtime_role_db.py``.
"""

from __future__ import annotations

import logging

import pytest

from app.core.config import Settings
from app.db.rls_runtime import (
    DatabaseRolePrivileges,
    UnsafeDatabaseRoleError,
    assert_role_enforces_rls,
)

SAFE = DatabaseRolePrivileges(role_name="ptd_app", is_superuser=False, bypasses_rls=False)


@pytest.mark.parametrize(
    ("is_superuser", "bypasses_rls", "expected"),
    [
        (False, False, True),
        (True, False, False),
        (False, True, False),
        (True, True, False),
    ],
)
def test_enforces_rls_only_for_plain_role(
    is_superuser: bool, bypasses_rls: bool, expected: bool
) -> None:
    privileges = DatabaseRolePrivileges(
        role_name="r", is_superuser=is_superuser, bypasses_rls=bypasses_rls
    )
    assert privileges.enforces_rls is expected


def test_describe_names_every_offending_attribute() -> None:
    both = DatabaseRolePrivileges(role_name="ptd", is_superuser=True, bypasses_rls=True)
    assert "SUPERUSER" in both.describe()
    assert "BYPASSRLS" in both.describe()
    assert "NOSUPERUSER NOBYPASSRLS" in SAFE.describe()


def test_safe_role_passes_when_enforcing() -> None:
    assert_role_enforces_rls(SAFE, enforce=True)


def test_none_is_not_applicable() -> None:
    """SQLite has no row security — nothing to verify, nothing to fail."""

    assert_role_enforces_rls(None, enforce=True)


@pytest.mark.parametrize(
    "privileges",
    [
        DatabaseRolePrivileges(role_name="ptd", is_superuser=True, bypasses_rls=False),
        DatabaseRolePrivileges(role_name="ptd", is_superuser=False, bypasses_rls=True),
    ],
)
def test_privileged_role_is_fatal_when_enforcing(privileges: DatabaseRolePrivileges) -> None:
    with pytest.raises(UnsafeDatabaseRoleError) as excinfo:
        assert_role_enforces_rls(privileges, enforce=True, component="api")
    # The message must be actionable, not just "denied".
    assert "provision_app_role.py" in str(excinfo.value)
    assert "MIGRATION_DATABASE_URL" in str(excinfo.value)


@pytest.fixture(autouse=True)
def _capture_rls_logger(caplog: pytest.LogCaptureFixture):
    """Цепляем обработчик caplog НАПРЯМУЮ к целевому логгеру: путь через root
    зависит от состояния, которое оставляют соседние тесты воркера (боевой
    logging-конфиг, propagate, уровни) — в CI записи терялись."""
    lg = logging.getLogger("app.db.rls_runtime")
    prev_disabled = lg.disabled
    lg.disabled = False
    lg.addHandler(caplog.handler)
    yield
    lg.removeHandler(caplog.handler)
    lg.disabled = prev_disabled


def test_privileged_role_only_warns_when_not_enforcing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    privileged = DatabaseRolePrivileges(role_name="ptd", is_superuser=True, bypasses_rls=False)
    with caplog.at_level(logging.WARNING, logger="app.db.rls_runtime"):
        assert_role_enforces_rls(privileged, enforce=False)
    assert any(record.message == "rls.runtime_role.unsafe" for record in caplog.records)


def test_membership_in_privileged_role_warns_but_passes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Attributes are not inherited, so this is a hardening note — not a failure."""

    escalatable = DatabaseRolePrivileges(
        role_name="ptd_app", is_superuser=False, bypasses_rls=False, can_escalate=True
    )
    with caplog.at_level(logging.WARNING, logger="app.db.rls_runtime"):
        assert_role_enforces_rls(escalatable, enforce=True)
    assert any(
        record.message == "rls.runtime_role.escalation_possible" for record in caplog.records
    )


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "SECRET_KEY": "unit-test-secret",
        "S3_ACCESS_KEY": "unit-test-access",
        "S3_SECRET_KEY": "unit-test-secret",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("app_env", "expected"),
    [("production", True), ("staging", True), ("development", False), ("test", False)],
)
def test_enforcement_defaults_to_deployed_environments(app_env: str, expected: bool) -> None:
    # ``model_copy`` swaps the env without re-running the production secret
    # validators — this test is about the enforcement default, not about them.
    settings = _settings().model_copy(update={"app_env": app_env})
    assert settings.rls_enforce_unprivileged_db_role is expected


@pytest.mark.parametrize("override", [True, False])
def test_explicit_override_wins(override: bool) -> None:
    settings = _settings(APP_ENV="development", RLS_REQUIRE_UNPRIVILEGED_DB_ROLE=override)
    assert settings.rls_enforce_unprivileged_db_role is override


def test_blank_env_var_means_unset() -> None:
    """``.env.example`` ships the key blank; that must not blow up settings loading."""

    settings = _settings(RLS_REQUIRE_UNPRIVILEGED_DB_ROLE="").model_copy(
        update={"app_env": "production"}
    )
    assert settings.rls_require_unprivileged_db_role_env is None
    assert settings.rls_enforce_unprivileged_db_role is True


def test_alembic_url_prefers_the_migration_role() -> None:
    """Alembic keeps the owner role: ENABLE/FORCE ROW LEVEL SECURITY is owner-only DDL."""

    settings = _settings(
        DATABASE_URL="postgresql+asyncpg://ptd_app:pw@db:5432/ptd",
        MIGRATION_DATABASE_URL="postgresql+asyncpg://ptd:pw@db:5432/ptd",
    )
    assert settings.database_url == "postgresql+asyncpg://ptd_app:pw@db:5432/ptd"
    assert settings.alembic_database_url == "postgresql+psycopg2://ptd:pw@db:5432/ptd"


def test_alembic_url_falls_back_to_database_url() -> None:
    settings = _settings(
        DATABASE_URL="postgresql+asyncpg://ptd:pw@db:5432/ptd",
        MIGRATION_DATABASE_URL="",
    )
    assert settings.alembic_database_url == "postgresql+psycopg2://ptd:pw@db:5432/ptd"


def test_redacted_settings_do_not_leak_database_passwords() -> None:
    settings = _settings(
        DATABASE_URL="postgresql+asyncpg://ptd_app:sup3rsecret@db:5432/ptd",
        MIGRATION_DATABASE_URL="postgresql+asyncpg://ptd:0wn3rsecret@db:5432/ptd",
    )
    payload = settings.redacted()
    assert payload["database_url_env"] == "***"
    assert payload["migration_database_url_env"] == "***"
    assert "sup3rsecret" not in repr(payload)
    assert "0wn3rsecret" not in repr(payload)
