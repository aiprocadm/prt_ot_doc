"""Breakdown управленческого дашборда: метрики в разрезе company/site/contractor.

Вычисляемый агрегат (P10-07 §24.2): на метрику — ОДИН SQL ``GROUP BY <dim_id>``
по живым таблицам, сшивка по id в Python, имена — из master-data. Не персистится,
ETag не нужен. Date-окно применяется ТОЛЬКО к incidents_open (occurred_at) —
overdue-метрики описывают состояние «на сегодня», окно к ним не применимо.
Contractor-разрез использует собственный набор метрик из
``ContractorReadinessReadModel`` (у пяти общих метрик нет FK на подрядчика).

None-bucket (site-разрез): ``Risk.site_id`` и ``Inspection.site_id`` nullable —
high-риски и просроченные предписания без привязки к объекту не должны тихо
исчезать из site-разреза (иначе итоги не сойдутся с executive-дашбордом).
Их счётчики собираются в синтетическую строку ``{"id": "", "name": "— без
объекта"}``, которая добавляется только когда хотя бы один её счётчик > 0 и
участвует в общей сортировке. ``Incident.site_id`` NOT NULL — инциденты в
None-bucket не попадают. Company-разрез: все company_id NOT NULL, bucket не нужен.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inspections import Inspection
from app.models.master_data import Company, Person, Site
from app.models.models import (
    Incident,
    IncidentStatus,
    PPEIssue,
    PPEIssueStatus,
    Prescription,
    TrainingPlan,
)
from app.models.risk import Risk
from app.modules.contractors.models import ContractorRegistry
from app.modules.projections.models import ContractorReadinessReadModel

BREAKDOWN_DIMENSIONS = ("company", "site", "contractor")
BREAKDOWN_ROW_CAP = 200

# Порог «высокого» риска — как в operational_dashboard/service.py:211
# (Risk.level >= 15). Шкала modules/risk/calc.py: high = 10-16, crit >= 17 —
# т.е. это top-slice high-диапазона плюс все критические.
HIGH_RISK_LEVEL_THRESHOLD = 15

NO_SITE_BUCKET_ID = ""
NO_SITE_BUCKET_NAME = "— без объекта"


async def _grouped_counts(session: AsyncSession, stmt) -> tuple[dict[str, int], int]:
    """Counts по ключу группировки + отдельный итог для key=None (None-bucket)."""

    rows = (await session.execute(stmt)).all()
    counts: dict[str, int] = {}
    none_total = 0
    for key, value in rows:
        if key is None:
            none_total += int(value or 0)
        else:
            counts[str(key)] = int(value or 0)
    return counts, none_total


async def compute_breakdown(
    session: AsyncSession,
    tenant_id: str,
    dimension: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    if dimension == "contractor":
        return await _contractor_breakdown(session, tenant_id)

    today = date.today()
    if dimension == "company":
        dim_incidents = Incident.company_id
        dim_risks = Risk.company_id
        dim_prescriptions = Inspection.company_id
    else:  # site
        dim_incidents = Incident.site_id
        dim_risks = Risk.site_id
        dim_prescriptions = Inspection.site_id

    incidents_stmt = (
        select(dim_incidents, func.count())
        .where(
            Incident.tenant_id == tenant_id,
            Incident.deleted_at.is_(None),
            Incident.status.notin_([IncidentStatus.CLOSED, IncidentStatus.CANCELLED]),
        )
        .group_by(dim_incidents)
    )
    if date_from is not None:
        incidents_stmt = incidents_stmt.where(func.date(Incident.occurred_at) >= date_from)
    if date_to is not None:
        incidents_stmt = incidents_stmt.where(func.date(Incident.occurred_at) <= date_to)

    risks_stmt = (
        select(dim_risks, func.count())
        .where(Risk.tenant_id == tenant_id, Risk.level >= HIGH_RISK_LEVEL_THRESHOLD)
        .group_by(dim_risks)
    )

    prescriptions_stmt = (
        select(dim_prescriptions, func.count())
        .select_from(Prescription)
        .join(Inspection, Inspection.id == Prescription.inspection_id)
        .where(
            Prescription.tenant_id == tenant_id,
            Prescription.deleted_at.is_(None),
            Prescription.due_at.is_not(None),
            Prescription.due_at < today,
        )
        .group_by(dim_prescriptions)
    )

    # Incident.site_id/company_id NOT NULL — none_total у инцидентов всегда 0.
    incidents, _ = await _grouped_counts(session, incidents_stmt)
    risks, risks_no_site = await _grouped_counts(session, risks_stmt)
    prescriptions, prescriptions_no_site = await _grouped_counts(session, prescriptions_stmt)

    trainings: dict[str, int] = {}
    ppe: dict[str, int] = {}
    if dimension == "company":
        trainings, _ = await _grouped_counts(
            session,
            select(TrainingPlan.company_id, func.count())
            .where(
                TrainingPlan.tenant_id == tenant_id,
                TrainingPlan.deleted_at.is_(None),
                TrainingPlan.due_date.is_not(None),
                TrainingPlan.due_date < today,
            )
            .group_by(TrainingPlan.company_id),
        )
        ppe, _ = await _grouped_counts(
            session,
            select(Person.company_id, func.count())
            .select_from(PPEIssue)
            .join(Person, Person.id == PPEIssue.person_id)
            .where(
                PPEIssue.tenant_id == tenant_id,
                PPEIssue.deleted_at.is_(None),
                PPEIssue.status == PPEIssueStatus.ISSUED.value,
                PPEIssue.expires_at.is_not(None),
                func.date(PPEIssue.expires_at) < today,
            )
            .group_by(Person.company_id),
        )

    entity_model = Company if dimension == "company" else Site
    entity_stmt = select(entity_model.id, entity_model.name).where(
        entity_model.tenant_id == tenant_id
    )
    if hasattr(entity_model, "deleted_at"):
        entity_stmt = entity_stmt.where(entity_model.deleted_at.is_(None))
    entities = (await session.execute(entity_stmt)).all()

    items: list[dict[str, Any]] = []
    for entity_id, name in entities:
        eid = str(entity_id)
        row: dict[str, Any] = {
            "id": eid,
            "name": name,
            "incidents_open": incidents.get(eid, 0),
            "prescriptions_overdue": prescriptions.get(eid, 0),
            "risks_high": risks.get(eid, 0),
        }
        total = row["incidents_open"] + row["prescriptions_overdue"] + row["risks_high"]
        if dimension == "company":
            row["trainings_overdue"] = trainings.get(eid, 0)
            row["ppe_overdue"] = ppe.get(eid, 0)
            total += row["trainings_overdue"] + row["ppe_overdue"]
        row["total_issues"] = total
        items.append(row)

    if dimension == "site" and (risks_no_site > 0 or prescriptions_no_site > 0):
        items.append(
            {
                "id": NO_SITE_BUCKET_ID,
                "name": NO_SITE_BUCKET_NAME,
                "incidents_open": 0,
                "prescriptions_overdue": prescriptions_no_site,
                "risks_high": risks_no_site,
                "total_issues": prescriptions_no_site + risks_no_site,
            }
        )

    items.sort(key=lambda r: (-r["total_issues"], r["name"]))
    return {"dimension": dimension, "items": items[:BREAKDOWN_ROW_CAP], "total": len(items)}


async def _contractor_breakdown(session: AsyncSession, tenant_id: str) -> dict[str, Any]:
    readiness_by_contractor = {
        row.contractor_id: row
        for row in (
            await session.execute(
                select(ContractorReadinessReadModel).where(
                    ContractorReadinessReadModel.tenant_id == tenant_id
                )
            )
        ).scalars()
    }
    registry = (
        await session.execute(
            select(ContractorRegistry.id, ContractorRegistry.name).where(
                ContractorRegistry.tenant_id == tenant_id,
                ContractorRegistry.deleted_at.is_(None),
            )
        )
    ).all()

    items: list[dict[str, Any]] = []
    for contractor_id, name in registry:
        r = readiness_by_contractor.get(contractor_id)
        row = {
            "id": str(contractor_id),
            "name": name,
            "workers_blocked": int(r.workers_blocked) if r else 0,
            "missing_docs": int(r.missing_docs_count) if r else 0,
            "missing_training": int(r.missing_training_count) if r else 0,
            "overdue_items": int(r.overdue_items_count) if r else 0,
            "active_packages": int(r.active_packages_count) if r else 0,
        }
        row["total_issues"] = (
            row["workers_blocked"]
            + row["missing_docs"]
            + row["missing_training"]
            + row["overdue_items"]
        )
        items.append(row)

    items.sort(key=lambda r: (-r["total_issues"], r["name"]))
    return {
        "dimension": "contractor",
        "items": items[:BREAKDOWN_ROW_CAP],
        "total": len(items),
    }
