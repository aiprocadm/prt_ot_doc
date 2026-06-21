"""wp06 guard: цепочка от wp05, колонка type_specific, honest downgrade."""
from __future__ import annotations

import importlib.util
from pathlib import Path

MIG = (
    Path(__file__).resolve().parents[1]
    / "backend/app/migrations/versions/20260621_wp06_work_permit_type_specific.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("wp06_mig", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_wp06_chain_and_revision():
    mod = _load()
    assert mod.revision == "20260621_wp06_work_permit_type_specific"
    assert mod.down_revision == "20260620_wp05_work_permit_closing"


def test_wp06_adds_type_specific_column():
    src = MIG.read_text(encoding="utf-8")
    assert '"work_permit"' in src
    assert "type_specific" in src


def test_wp06_downgrade_drops_column():
    src = MIG.read_text(encoding="utf-8")
    assert 'op.drop_column("work_permit", "type_specific")' in src
