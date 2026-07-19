"""Pin: so02 СОУТ class-history migration shape (P10-04 срез-2)."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app" / "migrations" / "versions" / "20260626_so02_sout_class_history.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("so02_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_revision_metadata() -> None:
    mod = _load()
    assert mod.revision == "20260626_so02_sout_class_history"
    assert mod.down_revision == "20260626_so01_sout"


def test_upgrade_downgrade_callable() -> None:
    mod = _load()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def _count_op_calls(text: str, attr: str) -> int:
    """Count real ``op.<attr>(...)`` calls. Counting raw substrings instead
    would also match mentions inside comments and docstrings."""
    return sum(
        1
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attr
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
    )


def test_creates_single_table_reusing_existing_enum() -> None:
    text = _MIGRATION.read_text(encoding="utf-8")
    assert '"sout_class_history"' in text
    assert _count_op_calls(text, "create_table") == 1
    assert _count_op_calls(text, "drop_table") == 1
    # soutclass owned by so01 → referenced, never re-created here
    assert "create_type=False" in text
    assert 'enum_type.create' not in text
