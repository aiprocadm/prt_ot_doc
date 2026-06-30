"""RC-012 — formal RTO/RPO go/no-go in the restore drill.

The full drill needs Postgres/MinIO and an app boot; the *decision* logic is
factored into the pure helper ``scripts.restore_drill.evaluate_rto_rpo`` so the
go/no-go criteria can be pinned here without any of that infrastructure.
"""

from __future__ import annotations

import importlib

restore_drill = importlib.import_module("scripts.restore_drill")


def _decide(**overrides):
    base = dict(
        rto_measured_seconds=10.0,
        rpo_measured_seconds=5.0,
        rto_threshold_seconds=14400,
        rpo_threshold_seconds=86400,
        integrity_ok=True,
    )
    base.update(overrides)
    return restore_drill.evaluate_rto_rpo(**base)


def test_go_when_objectives_met_and_integrity_ok() -> None:
    r = _decide()
    assert r["rto_met"] is True
    assert r["rpo_met"] is True
    assert r["decision"] == "go"


def test_no_go_when_rto_breached() -> None:
    r = _decide(rto_measured_seconds=20_000)  # > 4h budget
    assert r["rto_met"] is False
    assert r["decision"] == "no-go"


def test_no_go_when_rpo_breached() -> None:
    r = _decide(rpo_measured_seconds=90_000)  # > 24h budget
    assert r["rpo_met"] is False
    assert r["decision"] == "no-go"


def test_no_go_when_integrity_failed_even_if_objectives_met() -> None:
    # Objectives alone must NOT pass the drill — integrity is still required.
    r = _decide(integrity_ok=False)
    assert r["rto_met"] is True and r["rpo_met"] is True
    assert r["decision"] == "no-go"


def test_threshold_boundary_is_inclusive() -> None:
    # measured == threshold counts as met (<=).
    r = _decide(rto_measured_seconds=14400, rpo_measured_seconds=86400)
    assert r["rto_met"] is True and r["rpo_met"] is True
    assert r["decision"] == "go"


def test_defaults_align_with_tz_targets() -> None:
    # ТЗ vNext §31.6: RTO ≤ 4h, RPO ≤ 24h (when env override is not set).
    import os

    if not os.getenv("RESTORE_DRILL_RTO_SECONDS"):
        assert restore_drill.DEFAULT_RTO_SECONDS == 4 * 60 * 60
    if not os.getenv("RESTORE_DRILL_RPO_SECONDS"):
        assert restore_drill.DEFAULT_RPO_SECONDS == 24 * 60 * 60


def test_decision_block_has_full_shape() -> None:
    r = _decide()
    for key in (
        "rto_threshold_seconds",
        "rto_measured_seconds",
        "rto_met",
        "rpo_threshold_seconds",
        "rpo_measured_seconds",
        "rpo_met",
        "rpo_basis",
        "integrity_ok",
        "decision",
    ):
        assert key in r, f"missing key {key!r} in go_no_go block"
