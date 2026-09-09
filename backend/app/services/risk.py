"""Риски по площадке — по ЖИВЫМ оценкам (BIZ-54-57 срез-132).

До среза-132 эта служба читала реестр ``risk`` — таблицу, в которую не пишет
никто (опись среза-131). Ручка ``GET /risk/risks`` отвечала пустым списком
всегда, и пустота читалась как «рисков нет».

РЕШЕНИЕ О ШКАЛЕ (срез-131 оставил его открытым). Схема ответа держала
``probability`` и ``severity`` в пределах 1..5 — это шкала 5×5 мёртвого
реестра. У живой оценки шкалу задаёт МЕТОДОЛОГИЯ: у Fine-Kinney вероятность
идёт до 10, а последствия — до 100. Выбор был между «резать чужую шкалу под
свою» и «перестать врать про диапазон»:

* урезать нельзя — оценка по Fine-Kinney не влезет и ручка начнёт падать
  на живых данных;
* пересчитывать в 5×5 нельзя — это выдуманное число, которого нет ни в одном
  документе арендатора.

Поэтому нижняя граница осталась (нуля и отрицательных значений не бывает), а
верхняя убрана: диапазон принадлежит методологии, а не ручке. Числа берутся
ПОСЛЕ мер (``*_after``) — вопрос «что осталось», а не «что было до того, как
мы вмешались».
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Site, Tenant, Workplace
from app.models.risk import RiskAssessment, RiskHazard

__all__ = ["RiskService", "RiskLevelError", "RiskRow", "RiskSiteReport"]


class RiskLevelError(ValueError):
    """Raised when probability or severity values are out of supported bounds."""


@dataclass(frozen=True, slots=True)
class RiskRow:
    """Строка ответа ручки рисков.

    Отдельный тип, а не ORM-модель: у живой оценки другие имена полей
    (``likelihood_after``, ``score_after``, опасность — ссылкой на справочник),
    а договор ручки менять сверх необходимого незачем. Перевод имён живёт
    здесь, в одном месте.
    """

    id: str
    tenant_id: str
    company_id: str
    site_id: str | None
    hazard: str
    probability: int
    severity: int
    level: int
    controls: str | None


@dataclass(slots=True)
class RiskSiteReport:
    site_id: str | None
    total: int
    highest_level: int | None
    average_level: float | None
    distribution: dict[int, int]


class RiskService:
    """Помощники вокруг оценок рисков (``RiskAssessment``)."""

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
    ) -> tuple[list[RiskRow], RiskSiteReport | None]:
        """Оценки рисков арендатора, при необходимости — по одной площадке."""

        tenant_id = str(tenant.id)
        # Организация — по связям оценки: своя, затем площадки, затем рабочего
        # места. Договор ручки требует строку, а у оценки организация
        # необязательна: её заводят и на рабочее место, и на должность.
        company = func.coalesce(RiskAssessment.company_id, Site.company_id, Workplace.company_id)
        stmt: Select[tuple[RiskAssessment, str, str | None]] = (
            select(RiskAssessment, RiskHazard.title, company)
            .join(RiskHazard, RiskHazard.id == RiskAssessment.hazard_id)
            .outerjoin(Site, Site.id == RiskAssessment.place_id)
            .outerjoin(Workplace, Workplace.id == RiskAssessment.workplace_id)
            .where(RiskAssessment.tenant_id == tenant_id)
            .order_by(RiskAssessment.score_after.desc(), RiskAssessment.created_at.desc())
        )
        if site_id:
            stmt = stmt.where(RiskAssessment.place_id == site_id)

        risks = [
            RiskRow(
                id=str(assessment.id),
                tenant_id=str(assessment.tenant_id),
                # Пустая строка, а не пропуск строки: оценку без организации
                # теряют молча, а пустоту называют (приём разреза аналитики).
                company_id=company_id or "",
                site_id=assessment.place_id,
                hazard=hazard_title,
                probability=assessment.likelihood_after,
                severity=assessment.severity_after,
                level=assessment.score_after,
                controls=assessment.controls,
            )
            for assessment, hazard_title, company_id in (await session.execute(stmt)).all()
        ]

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
