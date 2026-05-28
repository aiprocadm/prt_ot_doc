"""Pin tests for ``scripts/audit/server_default_parity.py``.

The audit answers: **for every model column declared
``nullable=False, default=<literal>``, does the migration mirror it
with a matching ``server_default``?**

If not, raw-SQL INSERTs (perf scripts, restore-drill, manual fixes) hit
``NOT NULL`` violation because Python's ``default=`` only fires on ORM
inserts. iter-32 fixed exactly this for ``ppeissue.quantity`` via
``server_default="1"``; the audit's job is to find every other
instance of the same gap.

Detection rules:
  - **In-scope model column**: ``Mapped[T] = mapped_column(..., nullable=False, default=<literal or enum attribute>)``
    where ``default`` is one of:
      - ``ast.Constant`` (int/str/bool/None)
      - ``ast.Attribute`` (enum literal like ``RecordStatus.DRAFT``)
    Callable defaults (``default=uuid.uuid4``, ``default=datetime.utcnow``)
    are out of scope — they can't be translated to a DB-side default.
  - **OK if migration has server_default**: any ``sa.Column("col", ...,
    server_default=...)`` for the column counts as parity (text /
    sa.text(...) / int constant — all valid forms).
  - **Drift if migration column exists without server_default**: the
    column is in the migration as ``nullable=False`` but no
    ``server_default`` kwarg.

Tests are pure AST + tmpfile fixtures — no full app boot, runs on
Win+Py3.13 without the conftest crash.
"""

from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = REPO_ROOT / "scripts" / "audit" / "server_default_parity.py"


def _load_audit():
    if not AUDIT_PATH.exists():
        pytest.fail(f"server_default_parity.py audit script not found at {AUDIT_PATH}")
    spec = _ilu.spec_from_file_location("server_default_parity", AUDIT_PATH)
    assert spec is not None and spec.loader is not None
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Model-side scan
# ---------------------------------------------------------------------------


def test_scan_model_literal_int_default_nullable_false(tmp_path: Path) -> None:
    """`nullable=False, default=1` is in scope."""
    audit = _load_audit()
    src = tmp_path / "m.py"
    src.write_text(
        """
from app.models.base import TenantBaseModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer

class Foo(TenantBaseModel):
    __tablename__ = "foo"
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
""",
        encoding="utf-8",
    )
    found = audit.scan_model_default_candidates(src)
    assert ("foo", "quantity") in found
    assert found[("foo", "quantity")]["default_repr"] == "1"


def test_scan_model_literal_string_default_nullable_false(tmp_path: Path) -> None:
    audit = _load_audit()
    src = tmp_path / "m.py"
    src.write_text(
        """
from app.models.base import TenantBaseModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String

class Bar(TenantBaseModel):
    __tablename__ = "bar"
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
""",
        encoding="utf-8",
    )
    found = audit.scan_model_default_candidates(src)
    assert ("bar", "status") in found
    assert found[("bar", "status")]["default_repr"] == "'draft'"


def test_scan_model_enum_attribute_default_nullable_false(tmp_path: Path) -> None:
    """Enum literal defaults like RecordStatus.DRAFT are in scope."""
    audit = _load_audit()
    src = tmp_path / "m.py"
    src.write_text(
        """
from app.models.base import TenantBaseModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Enum

class Baz(TenantBaseModel):
    __tablename__ = "baz"
    status: Mapped["RecordStatus"] = mapped_column(Enum(RecordStatus), nullable=False, default=RecordStatus.DRAFT)
""",
        encoding="utf-8",
    )
    found = audit.scan_model_default_candidates(src)
    assert ("baz", "status") in found
    assert "RecordStatus.DRAFT" in found[("baz", "status")]["default_repr"]


def test_scan_model_callable_default_excluded(tmp_path: Path) -> None:
    """Callable defaults (uuid.uuid4, datetime.utcnow) can't translate to
    server_default; out of scope.
    """
    audit = _load_audit()
    src = tmp_path / "m.py"
    src.write_text(
        """
import uuid
from app.models.base import TenantBaseModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String

class Qux(TenantBaseModel):
    __tablename__ = "qux"
    id: Mapped[str] = mapped_column(String(36), nullable=False, default=uuid.uuid4)
""",
        encoding="utf-8",
    )
    found = audit.scan_model_default_candidates(src)
    assert ("qux", "id") not in found


def test_scan_model_nullable_true_excluded(tmp_path: Path) -> None:
    """Nullable columns: Python default is sugar, no DB invariant broken."""
    audit = _load_audit()
    src = tmp_path / "m.py"
    src.write_text(
        """
from app.models.base import TenantBaseModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer

class Nul(TenantBaseModel):
    __tablename__ = "nul"
    optional: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
""",
        encoding="utf-8",
    )
    found = audit.scan_model_default_candidates(src)
    assert ("nul", "optional") not in found


def test_scan_model_no_default_excluded(tmp_path: Path) -> None:
    """No model-side default means no parity expectation."""
    audit = _load_audit()
    src = tmp_path / "m.py"
    src.write_text(
        """
from app.models.base import TenantBaseModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer

class NoD(TenantBaseModel):
    __tablename__ = "nod"
    val: Mapped[int] = mapped_column(Integer, nullable=False)
""",
        encoding="utf-8",
    )
    found = audit.scan_model_default_candidates(src)
    assert ("nod", "val") not in found


def test_scan_model_default_tablename_inferred(tmp_path: Path) -> None:
    """When __tablename__ is absent, SQLAlchemy defaults to lowercased class name."""
    audit = _load_audit()
    src = tmp_path / "m.py"
    src.write_text(
        """
from app.models.base import TenantBaseModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer

class PPENorm(TenantBaseModel):
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
""",
        encoding="utf-8",
    )
    found = audit.scan_model_default_candidates(src)
    assert ("ppenorm", "quantity") in found, f"got {list(found)}"


# ---------------------------------------------------------------------------
# Migration-side scan
# ---------------------------------------------------------------------------


def test_scan_migration_column_with_server_default(tmp_path: Path) -> None:
    """Column with server_default=... satisfies parity."""
    audit = _load_audit()
    src = tmp_path / "mig.py"
    src.write_text(
        """
import sqlalchemy as sa
from alembic import op

def upgrade():
    op.create_table('foo',
        sa.Column('quantity', sa.Integer(), nullable=False, server_default="1"),
    )
""",
        encoding="utf-8",
    )
    info = audit.scan_migration_columns_with_defaults([src])
    assert "foo" in info
    assert info["foo"]["quantity"]["has_server_default"] is True


def test_scan_migration_column_without_server_default(tmp_path: Path) -> None:
    """Column with nullable=False but no server_default is a drift candidate."""
    audit = _load_audit()
    src = tmp_path / "mig.py"
    src.write_text(
        """
import sqlalchemy as sa
from alembic import op

def upgrade():
    op.create_table('foo',
        sa.Column('quantity', sa.Integer(), nullable=False),
    )
""",
        encoding="utf-8",
    )
    info = audit.scan_migration_columns_with_defaults([src])
    assert info["foo"]["quantity"]["has_server_default"] is False


def test_scan_migration_add_column_with_server_default(tmp_path: Path) -> None:
    """op.add_column also tracked."""
    audit = _load_audit()
    src = tmp_path / "mig.py"
    src.write_text(
        """
import sqlalchemy as sa
from alembic import op

def upgrade():
    op.add_column('foo', sa.Column('quantity', sa.Integer(), nullable=False, server_default="1"))
""",
        encoding="utf-8",
    )
    info = audit.scan_migration_columns_with_defaults([src])
    assert info["foo"]["quantity"]["has_server_default"] is True


# ---------------------------------------------------------------------------
# Integrated drift detection
# ---------------------------------------------------------------------------


def test_detect_drift_model_has_default_migration_missing_server_default(tmp_path: Path) -> None:
    """End-to-end: synthetic model+migration showing the drift class."""
    audit = _load_audit()
    model_src = tmp_path / "m.py"
    model_src.write_text(
        """
from app.models.base import TenantBaseModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer

class Foo(TenantBaseModel):
    __tablename__ = "foo"
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
""",
        encoding="utf-8",
    )
    mig_src = tmp_path / "mig.py"
    mig_src.write_text(
        """
import sqlalchemy as sa
from alembic import op

def upgrade():
    op.create_table('foo',
        sa.Column('quantity', sa.Integer(), nullable=False),
    )
""",
        encoding="utf-8",
    )
    drift = audit.detect_drift(model_src, [mig_src])
    assert ("foo", "quantity") in drift
    assert drift[("foo", "quantity")]["default_repr"] == "1"


def test_detect_no_drift_when_server_default_present(tmp_path: Path) -> None:
    audit = _load_audit()
    model_src = tmp_path / "m.py"
    model_src.write_text(
        """
from app.models.base import TenantBaseModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer

class Foo(TenantBaseModel):
    __tablename__ = "foo"
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
""",
        encoding="utf-8",
    )
    mig_src = tmp_path / "mig.py"
    mig_src.write_text(
        """
import sqlalchemy as sa
from alembic import op

def upgrade():
    op.create_table('foo',
        sa.Column('quantity', sa.Integer(), nullable=False, server_default="1"),
    )
""",
        encoding="utf-8",
    )
    drift = audit.detect_drift(model_src, [mig_src])
    assert ("foo", "quantity") not in drift


def test_detect_no_drift_when_column_absent_from_migration(tmp_path: Path) -> None:
    """If the column isn't in any migration at all, that's column_drift_lite's
    territory — server_default audit reports it as 'unknown' (no drift report).
    """
    audit = _load_audit()
    model_src = tmp_path / "m.py"
    model_src.write_text(
        """
from app.models.base import TenantBaseModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer

class Foo(TenantBaseModel):
    __tablename__ = "foo"
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
""",
        encoding="utf-8",
    )
    mig_src = tmp_path / "mig.py"
    mig_src.write_text(
        """
import sqlalchemy as sa
from alembic import op

def upgrade():
    op.create_table('foo',
        sa.Column('other_col', sa.Integer(), nullable=False),
    )
""",
        encoding="utf-8",
    )
    drift = audit.detect_drift(model_src, [mig_src])
    assert ("foo", "quantity") not in drift


# ---------------------------------------------------------------------------
# Real-codebase smoke (closed-loop verification)
# ---------------------------------------------------------------------------


def test_real_codebase_ppenorm_quantity_flagged() -> None:
    """Known instance: models.py:1291 PPENorm.quantity default=1, initial
    migration line 623 sa.Column('quantity', sa.Integer(), nullable=False)
    without server_default → must be flagged.
    """
    audit = _load_audit()
    drift = audit.run()
    assert ("ppenorm", "quantity") in drift, (
        f"ppenorm.quantity (known drift) should be flagged; got {sorted(drift)[:5]}..."
    )


def test_real_codebase_ppenorm_interval_days_flagged() -> None:
    """Known instance: models.py:1292 PPENorm.interval_days default=365,
    initial migration line 624 nullable=False no server_default.
    """
    audit = _load_audit()
    drift = audit.run()
    assert ("ppenorm", "interval_days") in drift, (
        f"ppenorm.interval_days (known drift) should be flagged; got {sorted(drift)[:5]}..."
    )


def test_real_codebase_ppeissue_quantity_NOT_flagged() -> None:
    """iter-32 added server_default='1' for ppeissue.quantity — must NOT
    be flagged (parity now satisfied).
    """
    audit = _load_audit()
    drift = audit.run()
    assert ("ppeissue", "quantity") not in drift, (
        "ppeissue.quantity has iter-32's server_default — should NOT be in drift"
    )
