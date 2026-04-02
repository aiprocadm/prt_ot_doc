"""Schemas describing tenant risk register entries."""

from __future__ import annotations

from dataclasses import asdict

from pydantic import BaseModel, Field

from app.services.risk import RiskSiteReport


class RiskRead(BaseModel):
    id: str
    tenant_id: str
    company_id: str
    site_id: str | None = None
    hazard: str
    probability: int = Field(ge=1, le=5)
    severity: int = Field(ge=1, le=5)
    level: int
    controls: str | None = None

    model_config = {
        "from_attributes": True,
    }


class RiskReport(BaseModel):
    site_id: str | None = None
    total: int
    highest_level: int | None = None
    average_level: float | None = None
    distribution: dict[int, int]

    @classmethod
    def from_service(cls, report: RiskSiteReport) -> "RiskReport":
        return cls(**asdict(report))


class RiskListResponse(BaseModel):
    items: list[RiskRead]
    report: RiskReport | None = None

    @classmethod
    def from_entities(
        cls, risks: list[object], report: RiskSiteReport | None
    ) -> "RiskListResponse":
        return cls(
            items=[RiskRead.model_validate(risk, from_attributes=True) for risk in risks],
            report=RiskReport.from_service(report) if report else None,
        )
