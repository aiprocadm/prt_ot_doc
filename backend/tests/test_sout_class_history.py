"""Unit + API: СОУТ class-of-conditions history (P10-04 срез-2)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import sout as routes
from app.domains.sout.lifecycle import CLASS_SEVERITY, is_class_worsening
from app.domains.sout.service import build_class_history_row, history_to_read
from app.models.sout import SoutClass, SoutClassHistory
from app.schemas.sout import WorkplaceUpdate


# ── model shape ──────────────────────────────────────────────────────────────

def test_class_history_table_and_columns() -> None:
    assert SoutClassHistory.__tablename__ == "sout_class_history"
    cols = set(SoutClassHistory.__table__.columns.keys())
    assert {
        "id", "tenant_id", "workplace_id", "old_class", "new_class",
        "changed_at", "note",
    } <= cols


def test_history_reuses_shared_soutclass_enum() -> None:
    assert SoutClassHistory.__table__.columns["old_class"].type.name == "soutclass"
    assert SoutClassHistory.__table__.columns["new_class"].type.name == "soutclass"


# ── severity / worsening ─────────────────────────────────────────────────────

def test_severity_is_monotonic_optimal_to_dangerous() -> None:
    order = [
        SoutClass.OPTIMAL, SoutClass.ACCEPTABLE, SoutClass.HARMFUL_3_1,
        SoutClass.HARMFUL_3_2, SoutClass.HARMFUL_3_3, SoutClass.HARMFUL_3_4,
        SoutClass.DANGEROUS,
    ]
    ranks = [CLASS_SEVERITY[c] for c in order]
    assert ranks == sorted(ranks)
    assert len(set(ranks)) == len(ranks)  # strictly increasing


def test_worsening_true_when_class_more_severe() -> None:
    assert is_class_worsening(SoutClass.ACCEPTABLE, SoutClass.HARMFUL_3_2) is True


def test_worsening_false_when_improving() -> None:
    assert is_class_worsening(SoutClass.HARMFUL_3_2, SoutClass.ACCEPTABLE) is False


def test_worsening_false_on_first_assessment() -> None:
    assert is_class_worsening(None, SoutClass.DANGEROUS) is False


def test_worsening_false_when_new_unknown() -> None:
    assert is_class_worsening(SoutClass.OPTIMAL, None) is False


# ── service helpers ──────────────────────────────────────────────────────────

def test_build_history_row_none_when_unchanged() -> None:
    assert build_class_history_row(
        tenant_id="t1", workplace_id="w1",
        old_class=SoutClass.HARMFUL_3_1, new_class=SoutClass.HARMFUL_3_1,
    ) is None


def test_build_history_row_created_on_change() -> None:
    row = build_class_history_row(
        tenant_id="t1", workplace_id="w1",
        old_class=SoutClass.ACCEPTABLE, new_class=SoutClass.HARMFUL_3_3,
    )
    assert row is not None
    assert row.tenant_id == "t1"
    assert row.old_class is SoutClass.ACCEPTABLE
    assert row.new_class is SoutClass.HARMFUL_3_3


def test_build_history_row_initial_assignment() -> None:
    row = build_class_history_row(
        tenant_id="t1", workplace_id="w1", old_class=None, new_class=SoutClass.OPTIMAL,
    )
    assert row is not None
    assert row.old_class is None


def test_history_to_read_marks_worsening() -> None:
    raw = SimpleNamespace(
        id="h1", workplace_id="w1",
        old_class=SoutClass.ACCEPTABLE, new_class=SoutClass.HARMFUL_3_2,
        changed_at=datetime(2026, 6, 26, tzinfo=timezone.utc), note=None,
    )
    read = history_to_read(raw)
    assert read.is_worsening is True


# ── API: PATCH records history on class change ──────────────────────────────

def _tenant():
    return SimpleNamespace(id="tenant-1", is_active=True, slug="t1")


def _workplace(assessed_class=SoutClass.ACCEPTABLE):
    now = datetime(2026, 6, 26, tzinfo=timezone.utc)
    return SimpleNamespace(
        id="w1", campaign_id="c1", tenant_id="tenant-1",
        workplace_code="РМ-001", position_name="Сварщик", person_id=None,
        assessed_class=assessed_class, assessment_date=None, next_assessment_date=None,
        created_at=now, updated_at=now, deleted_at=None,
    )


@pytest.mark.asyncio
async def test_update_workplace_records_history_on_class_change(monkeypatch):
    wp = _workplace(SoutClass.ACCEPTABLE)
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "_get_workplace", AsyncMock(return_value=wp))

    added: list = []
    session = AsyncMock()
    session.add = lambda obj: added.append(obj)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    await routes.update_workplace(
        wid="w1",
        payload=WorkplaceUpdate(assessed_class=SoutClass.HARMFUL_3_2),
        tenant=_tenant(), session=session, access=SimpleNamespace(),
    )
    hist = [o for o in added if isinstance(o, SoutClassHistory)]
    assert len(hist) == 1
    assert hist[0].old_class is SoutClass.ACCEPTABLE
    assert hist[0].new_class is SoutClass.HARMFUL_3_2


@pytest.mark.asyncio
async def test_update_workplace_no_history_when_class_untouched(monkeypatch):
    wp = _workplace(SoutClass.ACCEPTABLE)
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "_get_workplace", AsyncMock(return_value=wp))

    added: list = []
    session = AsyncMock()
    session.add = lambda obj: added.append(obj)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    # update only the position, not the class
    await routes.update_workplace(
        wid="w1",
        payload=WorkplaceUpdate(position_name="Электрик"),
        tenant=_tenant(), session=session, access=SimpleNamespace(),
    )
    assert [o for o in added if isinstance(o, SoutClassHistory)] == []


@pytest.mark.asyncio
async def test_update_workplace_no_history_when_same_class(monkeypatch):
    wp = _workplace(SoutClass.HARMFUL_3_1)
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "_get_workplace", AsyncMock(return_value=wp))

    added: list = []
    session = AsyncMock()
    session.add = lambda obj: added.append(obj)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    await routes.update_workplace(
        wid="w1",
        payload=WorkplaceUpdate(assessed_class=SoutClass.HARMFUL_3_1),
        tenant=_tenant(), session=session, access=SimpleNamespace(),
    )
    assert [o for o in added if isinstance(o, SoutClassHistory)] == []
