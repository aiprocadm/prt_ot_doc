"""wp05 guard: цепочка от истинного head, состав колонок, honest downgrade."""
from __future__ import annotations

import importlib.util
from pathlib import Path

MIG = (
    Path(__file__).resolve().parents[1]
    / "backend/app/migrations/versions/20260620_wp05_work_permit_closing.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("wp05_mig", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_wp05_chain_and_revision():
    mod = _load()
    assert mod.revision == "20260620_wp05_work_permit_closing"
    assert mod.down_revision == "20260618_wp04_work_permit_ops_journal"


def test_wp05_adds_completion_columns():
    src = MIG.read_text(encoding="utf-8")
    # table name LITERAL (AST-audit blindspot)
    assert '"work_permit"' in src
    assert "completion_text" in src
    assert "completion_recorded_at" in src


def test_wp05_downgrade_drops_added_columns():
    src = MIG.read_text(encoding="utf-8")
    assert 'op.drop_column("work_permit", "completion_text")' in src
    assert 'op.drop_column("work_permit", "completion_recorded_at")' in src
