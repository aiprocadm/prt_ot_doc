"""so03 guard: single-head chain + bridge column shape (P10-04 срез-3)."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_REVISION = "20260626_so03_sout_norm_bridges"
_DOWN = "20260626_so02_sout_class_history"


def _script_dir() -> ScriptDirectory:
    root = Path(__file__).resolve().parents[1] / "app"
    cfg = Config()
    cfg.set_main_option("script_location", str(root / "migrations"))
    return ScriptDirectory.from_config(cfg)


def test_so03_chains_from_so02_and_is_single_head() -> None:
    sd = _script_dir()
    rev = sd.get_revision(_REVISION)
    assert rev.down_revision == _DOWN
    heads = sd.get_heads()
    assert len(heads) == 1, f"expected single head, got {heads}"
    # so03 was the head when this pin was written; later slices chain after it.
    # What must stay true is that it is still on the single chain — i.e. an
    # ancestor of whatever the current head is, not a stranded branch.
    ancestry = {r.revision for r in sd.iterate_revisions(heads[0], "base")}
    assert _REVISION in ancestry, f"{_REVISION} is not an ancestor of head {heads[0]}"


def test_so03_module_defines_both_bridge_columns() -> None:
    text = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "migrations"
        / "versions"
        / "20260626_so03_sout_norm_bridges.py"
    ).read_text(encoding="utf-8")
    assert 'add_column("sout_workplace"' in text
    assert 'add_column("sout_factor"' in text
    assert '"position_id"' in text
    assert '"hazard_id"' in text
    assert "create_foreign_key" in text
    assert '"position"' in text
    assert '"risk_hazards"' in text
    assert 'ondelete="SET NULL"' in text
    assert 'drop_column("sout_workplace", "position_id")' in text
    assert 'drop_column("sout_factor", "hazard_id")' in text
    assert "drop_constraint" in text
