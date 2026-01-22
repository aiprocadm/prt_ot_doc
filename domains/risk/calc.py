from __future__ import annotations

from collections import defaultdict
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RiskMethodology
from app.models.risk import RiskAssessment, RiskMatrixCell

Band = Literal["low", "med", "high", "crit"]


def _fallback_band(score: int) -> Band:
    if score <= 4:
        return "low"
    if score <= 9:
        return "med"
    if score <= 16:
        return "high"
    return "crit"


async def score_band(
    session: AsyncSession,
    tenant_id: str,
    severity: int,
    likelihood: int,
) -> tuple[int, Band]:
    """Return a risk score and qualitative band for the provided inputs."""

    stmt = select(RiskMatrixCell).where(
        RiskMatrixCell.tenant_id == tenant_id,
        RiskMatrixCell.severity == severity,
        RiskMatrixCell.likelihood == likelihood,
    )
    cell = (await session.execute(stmt)).scalar_one_or_none()
    if cell is None:
        score = int(severity) * int(likelihood)
        return score, _fallback_band(score)

    band_value = cell.band
    if band_value not in ("low", "med", "high", "crit"):
        band_value = _fallback_band(cell.score)
    return cell.score, cast(Band, band_value)


def _scale_values(definition: dict[str, object], key: str) -> list[int]:
    values: list[int] = []
    raw = definition.get(key, []) if isinstance(definition, dict) else []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, int):
                values.append(item)
            elif isinstance(item, dict) and "value" in item and isinstance(
                item["value"], int
            ):
                values.append(int(item["value"]))
    if not values:
        return [1, 2, 3, 4, 5]
    return sorted(set(values))


def _band_from_definition(definition: dict[str, object], score: int) -> Band:
    raw_bands = definition.get("bands", []) if isinstance(definition, dict) else []
    if isinstance(raw_bands, list):
        sorted_bands: list[tuple[int, Band]] = []
        for candidate in raw_bands:
            if not isinstance(candidate, dict):
                continue
            name = candidate.get("name")
            limit = candidate.get("max")
            if name in ("low", "med", "high", "crit") and isinstance(limit, int):
                sorted_bands.append((limit, cast(Band, name)))
        for limit, band in sorted(sorted_bands, key=lambda pair: pair[0]):
            if score <= limit:
                return band
    return _fallback_band(score)


async def rebuild_matrix_from_methodology(
    session: AsyncSession, tenant_id: str, methodology: RiskMethodology
) -> list[RiskMatrixCell]:
    """Create a full grid of matrix cells based on the methodology scales."""

    definition = methodology.definition or {}
    severities = _scale_values(definition, "severity_scale")
    likelihoods = _scale_values(definition, "likelihood_scale")

    await session.execute(
        select(RiskMatrixCell).where(RiskMatrixCell.tenant_id == tenant_id)
    )
    await session.execute(
        RiskMatrixCell.__table__.delete().where(RiskMatrixCell.tenant_id == tenant_id)
    )

    cells: list[RiskMatrixCell] = []
    for severity in severities:
        for likelihood in likelihoods:
            score = int(severity) * int(likelihood)
            band = _band_from_definition(definition, score)
            cells.append(
                RiskMatrixCell(
                    tenant_id=tenant_id,
                    severity=severity,
                    likelihood=likelihood,
                    score=score,
                    band=band,
                )
            )
    session.add_all(cells)
    await session.flush()
    return cells


async def recalc_risk_map(
    session: AsyncSession,
    tenant_id: str,
    methodology: RiskMethodology,
    *,
    company_id: str,
    site_id: str | None = None,
    position_id: str | None = None,
    document_pack_id: str | None = None,
) -> dict[str, object]:
    """Aggregate risk assessments into a matrix suitable for storing in RiskMap."""

    definition = methodology.definition or {}
    severities = _scale_values(definition, "severity_scale")
    likelihoods = _scale_values(definition, "likelihood_scale")

    stmt = select(RiskAssessment).where(
        RiskAssessment.tenant_id == tenant_id,
        RiskAssessment.company_id == company_id,
    )
    if site_id:
        stmt = stmt.where(RiskAssessment.place_id == site_id)
    if position_id:
        stmt = stmt.where(RiskAssessment.position_id == position_id)
    if document_pack_id:
        stmt = stmt.where(RiskAssessment.document_pack_id == document_pack_id)

    assessments = (await session.execute(stmt)).scalars().all()
    counts: dict[tuple[int, int], list[RiskAssessment]] = defaultdict(list)
    for assessment in assessments:
        counts[(assessment.severity_after, assessment.likelihood_after)].append(
            assessment
        )

    matrix_cells: list[dict[str, object]] = []
    for severity in severities:
        for likelihood in likelihoods:
            score, band = await score_band(session, tenant_id, severity, likelihood)
            cell_assessments = counts.get((severity, likelihood), [])
            hazards = [
                {
                    "hazard_id": assessment.hazard_id,
                    "assessment_id": assessment.id,
                }
                for assessment in cell_assessments
            ]
            matrix_cells.append(
                {
                    "severity": severity,
                    "likelihood": likelihood,
                    "score": score,
                    "band": band,
                    "count": len(cell_assessments),
                    "assessments": hazards,
                }
            )

    return {
        "methodology_id": str(methodology.id),
        "severities": severities,
        "likelihoods": likelihoods,
        "cells": matrix_cells,
        "total_assessments": len(assessments),
        "scope": {
            "company_id": company_id,
            "site_id": site_id,
            "position_id": position_id,
            "document_pack_id": document_pack_id,
        },
    }
