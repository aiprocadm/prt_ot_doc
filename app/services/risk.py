"""Risk assessment utilities."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Site, Tenant
from app.models.risk import Risk

__all__ = ["RiskService", "RiskLevelError", "RiskSiteReport"]


class RiskLevelError(ValueError):
    """Raised when probability or severity values are out of supported bounds."""


@dataclass(slots=True)
class RiskSiteReport:
    site_id: str | None
    total: int
    highest_level: int | None
    average_level: float | None
    distribution: dict[int, int]


class RiskService:
    """High-level helpers around :class:`~app.models.risk.Risk` objects."""

    MIN_SCORE = 1
    MAX_SCORE = 5

    @classmethod
    def calculate(cls, probability: int, severity: int) -> int:
        """Return a risk level score given probability and severity values."""

        cls._ensure_bounds(probability, "probability")
        cls._ensure_bounds(severity, "severity")
        return probability * severity

    @classmethod
    def _ensure_bounds(cls, value: int, field: str) -> None:
        if not cls.MIN_SCORE <= value <= cls.MAX_SCORE:
            raise RiskLevelError(
                f"{field} must be between {cls.MIN_SCORE} and {cls.MAX_SCORE}, got {value}"
            )

    @staticmethod
    async def list_by_site(
        session: AsyncSession,
        tenant: Tenant,
        site_id: str | None,
    ) -> tuple[list[Risk], RiskSiteReport | None]:
        """Fetch risks for a tenant optionally scoped to a site and calculate a report."""

        tenant_id = str(tenant.id)
        stmt: Select[tuple[Risk]] = (
            select(Risk)
            .where(Risk.tenant_id == tenant_id)
            .options(selectinload(Risk.site))
            .order_by(Risk.level.desc(), Risk.created_at.desc())
        )
        if site_id:
            stmt = stmt.where(Risk.site_id == site_id)

        risks = list((await session.execute(stmt)).scalars().unique().all())

        if not risks:
            return risks, None

        total = len(risks)
        highest = max(risk.level for risk in risks) if risks else None
        average = sum(risk.level for risk in risks) / total if risks else None
        distribution = Counter(risk.level for risk in risks)

        report = RiskSiteReport(
            site_id=site_id,
            total=total,
            highest_level=highest,
            average_level=round(average, 2) if average is not None else None,
            distribution=dict(sorted(distribution.items())),
        )
        return risks, report

    @staticmethod
    async def ensure_site_belongs_to_tenant(
        session: AsyncSession,
        tenant: Tenant,
        site_id: str,
    ) -> Site:
        stmt = select(Site).where(Site.id == site_id, Site.tenant_id == str(tenant.id))
        site = (await session.execute(stmt)).scalar_one_or_none()
        if site is None:
            raise LookupError("Site not found for tenant")
        return site
