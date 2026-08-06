"""Unit test for the native_enum() helper: it must produce an Enum that binds
the member .value (lowercase/CamelCase), not the member NAME — AND a *named*
PG type. An unnamed native enum makes ``metadata.create_all`` fail on
PostgreSQL at app startup with ``CompileError: AsyncPgEnum type requires a
name`` (surfaced by the perf-smoke job once CI was re-enabled)."""

from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum

from app.models.base import native_enum


class _Color(str, enum.Enum):
    RED = "red"
    DARK_BLUE = "dark_blue"


def test_native_enum_binds_values_not_names() -> None:
    t = native_enum(_Color, name="color")
    assert list(t.enums) == ["red", "dark_blue"]  # .value, not NAME
    assert t.name == "color"
    assert t.enum_class is _Color


def test_native_enum_derives_name_when_omitted() -> None:
    t = native_enum(_Color)
    assert list(t.enums) == ["red", "dark_blue"]
    # Regression guard: SQLAlchemy only derives the type name from the enum
    # class when "name" is NOT in kwargs. Passing name=None through to Enum()
    # suppresses that derivation → name=None → PG create_all CompileError.
    assert t.name == "_color"


def test_no_unnamed_native_enums_in_metadata() -> None:
    """Whole-registry guard: a native (PG) enum with name=None cannot be
    CREATE TYPE'd, so SharedBase/TenantBase.metadata.create_all() fails on
    PostgreSQL at app startup (aensure_shared_schema -> _create_shared_schema).
    Invisible on SQLite (no named types) and on the alembic path (migrations
    name enums explicitly), so only this ORM create_all guard catches it."""
    import app.db.base  # noqa: F401  triggers all model imports incl. app.modules.*
    from app.db.session import SharedBase, TenantBase

    offenders: list[str] = []
    for md in (SharedBase.metadata, TenantBase.metadata):
        for table in md.tables.values():
            for col in table.columns:
                typ = col.type
                if (
                    isinstance(typ, SAEnum)
                    and getattr(typ, "native_enum", False)
                    and typ.name is None
                ):
                    offenders.append(f"{table.name}.{col.name}")
    assert not offenders, (
        "native PG enum columns with no type name (metadata.create_all fails "
        "on PostgreSQL): " + ", ".join(sorted(offenders))
    )
