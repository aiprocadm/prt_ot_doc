from __future__ import annotations

import pytest

from app.domains.risk.calc import _fallback_band, score_band
from app.models.risk import RiskMatrixCell


@pytest.mark.parametrize(
    "score, expected",
    [(1, "low"), (6, "med"), (12, "high"), (25, "crit")],
)
def test_fallback_band(score: int, expected: str) -> None:
    assert _fallback_band(score) == expected


@pytest.mark.anyio()
async def test_score_band_uses_matrix_entry(sessionmaker) -> None:
    async with sessionmaker() as session:
        cell = RiskMatrixCell(
            tenant_id="tenant",
            severity=3,
            likelihood=4,
            score=42,
            band="high",
        )
        session.add(cell)
        await session.commit()

    async with sessionmaker() as session:
        score, band = await score_band(session, "tenant", severity=3, likelihood=4)
        assert score == 42
        assert band == "high"


@pytest.mark.anyio()
async def test_score_band_falls_back_for_unknown_entry(sessionmaker) -> None:
    async with sessionmaker() as session:
        score, band = await score_band(session, "tenant", severity=5, likelihood=4)
        assert score == 20
        assert band == "crit"


@pytest.mark.anyio()
async def test_score_band_handles_invalid_band(sessionmaker) -> None:
    async with sessionmaker() as session:
        cell = RiskMatrixCell(
            tenant_id="tenant",
            severity=1,
            likelihood=2,
            score=3,
            band="unexpected",
        )
        session.add(cell)
        await session.commit()

    async with sessionmaker() as session:
        score, band = await score_band(session, "tenant", severity=1, likelihood=2)
        assert score == 3
        assert band == "low"
