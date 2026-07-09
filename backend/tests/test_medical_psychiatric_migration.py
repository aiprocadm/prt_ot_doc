"""med03 migration is additive, round-trip-safe, chains from the wh01 head."""

from __future__ import annotations

from pathlib import Path

MIG = (
    Path(__file__).resolve().parents[2]
    / "backend/app/migrations/versions/20260709_med03_psychiatric_342n.py"
)


def _norm(text: str) -> str:
    return "".join(text.split())


def test_med03_chains_and_is_additive():
    src = MIG.read_text(encoding="utf-8")
    n = _norm(src)
    assert 'revision="20260709_med03_psychiatric_342n"' in n
    assert 'down_revision="20260709_wh01_webhook_delivery_outbox_id"' in n
    # creates both tables + adds both exam columns
    assert 'create_table("psychiatric_activity_type"' in n
    assert 'create_table("psychiatric_position_activity"' in n
    assert 'add_column("medical_exam"' in n
    assert n.count('add_column("medical_exam"') == 2
    # downgrade drops columns before tables (round-trip safe)
    assert 'drop_table("psychiatric_position_activity")' in n
    assert 'drop_table("psychiatric_activity_type")' in n
    assert 'drop_column("medical_exam","psychiatric_activity_codes")' in n
    assert 'drop_column("medical_exam","psychiatric_protocol_no")' in n
    # load-bearing server defaults (JSON '[]' + 5y periodicity) are pinned
    assert 'server_default="[]"' in n
    assert 'server_default="1825"' in n
    # the only cross-table reference is the position FK
    assert '["position.id"]' in n
