"""Schemas describing tenant risk register entries."""

from __future__ import annotations

from dataclasses import asdict

from pydantic import BaseModel, Field

from app.services.risk import RiskSiteReport


class RiskRead(BaseModel):
    """Оценка риска в ответе ручки.

    Срез-132: верхняя граница шкалы убрана — её задаёт МЕТОДОЛОГИЯ, а не
    ручка. Прежние ``le=5`` описывали шкалу 5×5 мёртвого реестра ``risk``;
    у Fine-Kinney вероятность идёт до 10, а последствия — до 100, и такая
    оценка в старый предел просто не влезала. Нижняя граница осталась:
    нулевой и отрицательной оценки не бывает ни в одной методологии.

    ``company_id`` ОСТАЛСЯ обязательным: сделать его пустым значило бы сменить
    тип поля в опубликованном ответе, а это ломающее изменение — ему место в
    новой мажорной версии (``docs/API_VERSIONING.md``). Организация берётся по
    связям оценки, а когда её нет ни по одной — пустой строкой, как «— без
    объекта» в разрезе аналитики: строку теряют молча, а пустоту называют.
    """

    id: str
    tenant_id: str
    company_id: str
    site_id: str | None = None
    hazard: str
    probability: int = Field(ge=1)
    severity: int = Field(ge=1)
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
