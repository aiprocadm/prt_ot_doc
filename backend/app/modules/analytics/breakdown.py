"""Breakdown управленческого дашборда: метрики в разрезе company/site/contractor.

Вычисляемый агрегат (P10-07 §24.2): на метрику — ОДИН SQL ``GROUP BY <dim_id>``
по живым таблицам, сшивка по id в Python, имена — из master-data. Не персистится,
ETag не нужен. Date-окно применяется ТОЛЬКО к incidents_open (occurred_at) —
overdue-метрики описывают состояние «на сегодня», окно к ним не применимо.
Contractor-разрез использует собственный набор метрик из
``ContractorReadinessReadModel`` (у пяти общих метрик нет FK на подрядчика).

Discipline-разрез (Доп. №1 разд. 57.4, «директорский» взгляд на всю
безопасность): строка на КАЖДУЮ дисциплину общего словаря, открытые
происшествия — по разметке ``Incident.discipline`` (неразмеченные — в
синтетическую строку «— не размечено», а НЕ в «охрану труда»), просрочки — из
той же формулы, что у Центра внимания (``services.discipline_attention``).
У дисциплины без размеченных источников сроков просрочка ``None``: это
«не считается», а не ноль — ноль читался бы как «нарушений нет».
Дисциплины вне редакции арендатора (модуль не выдан или выключен, приёмка
§58.3, срез-56): ПУСТАЯ строка убирается, строка с фактами остаётся —
происшествие случилось независимо от того, что куплено; скрытое названо в
``not_applicable`` одной фразой.

None-bucket (site-разрез): ``RiskAssessment.place_id`` и ``Inspection.site_id``
nullable —
high-риски и просроченные предписания без привязки к объекту не должны тихо
исчезать из site-разреза (иначе итоги не сойдутся с executive-дашбордом).
Их счётчики собираются в синтетическую строку ``{"id": "", "name": "— без
объекта"}``, которая добавляется только когда хотя бы один её счётчик > 0 и
участвует в общей сортировке. ``Incident.site_id`` NOT NULL — инциденты в
None-bucket не попадают. Company-разрез: все company_id NOT NULL, bucket не нужен.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.disciplines import DISCIPLINE_TITLES, Discipline
from app.models.inspections import Inspection
from app.models.master_data import Company, Person, Site
from app.models.models import (
    Incident,
    PPEIssue,
    PPEIssueStatus,
    Prescription,
    TrainingPlan,
)
from app.models.risk import RiskAssessment, RiskAssessmentItem
from app.modules.contractors.models import ContractorRegistry
from app.modules.projections.models import ContractorReadinessReadModel
from app.services.discipline_applicability import collect_applicability, describe_hidden
from app.services.discipline_attention import (
    ATTENTION_DISCIPLINES,
    attention_events,
    overdue_by_discipline,
)
from app.services.discipline_incidents import open_incidents_where
from app.services.discipline_risks import high_risk_item_where
from app.services.person_scope import employed_person_where, employed_record_where

BREAKDOWN_DIMENSIONS = ("company", "site", "contractor", "discipline")
BREAKDOWN_ROW_CAP = 200

NO_SITE_BUCKET_ID = ""
NO_SITE_BUCKET_NAME = "— без объекта"

NO_DISCIPLINE_BUCKET_ID = ""
NO_DISCIPLINE_BUCKET_NAME = "— не размечено"


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
    if dimension == "discipline":
        return await _discipline_breakdown(session, tenant_id, date_from=date_from, date_to=date_to)

    today = date.today()
    if dimension == "company":
        dim_incidents = Incident.company_id
        # Срез-131: разрез по рискам считался по таблице `risk`, в которую не
        # пишет никто, — то есть был нулём всегда. Живые данные лежат в
        # оценках рисков; площадка у оценки называется `place_id`.
        dim_risks = RiskAssessment.company_id
        dim_prescriptions = Inspection.company_id
    else:  # site
        dim_incidents = Incident.site_id
        dim_risks = RiskAssessment.place_id
        dim_prescriptions = Inspection.site_id

    incidents_stmt = (
        select(dim_incidents, func.count())
        .where(
            *open_incidents_where(tenant_id),
        )
        .group_by(dim_incidents)
    )
    if date_from is not None:
        incidents_stmt = incidents_stmt.where(func.date(Incident.occurred_at) >= date_from)
    if date_to is not None:
        incidents_stmt = incidents_stmt.where(func.date(Incident.occurred_at) <= date_to)

    # Формула «высокий риск» одна с KPI отчётов (срез-131): считаются СТРОКИ
    # оценки, а не оценки целиком — одна оценка описывает много опасностей.
    risks_stmt = (
        select(dim_risks, func.count())
        .select_from(RiskAssessmentItem)
        .join(RiskAssessment, RiskAssessment.id == RiskAssessmentItem.assessment_id)
        .where(*high_risk_item_where(tenant_id))
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
        # «Уволенный не в счёт» (BIZ-54-57 срез-96) — те же цифры, что в
        # виджете «просрочено», только по организациям.
        trainings, _ = await _grouped_counts(
            session,
            select(TrainingPlan.company_id, func.count())
            .where(
                TrainingPlan.tenant_id == tenant_id,
                TrainingPlan.deleted_at.is_(None),
                TrainingPlan.due_date.is_not(None),
                TrainingPlan.due_date < today,
                employed_record_where(TrainingPlan, tenant_id),
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
                *employed_person_where(),
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


async def _discipline_breakdown(
    session: AsyncSession,
    tenant_id: str,
    *,
    date_from: date | None,
    date_to: date | None,
) -> dict[str, Any]:
    incidents_stmt = (
        select(Incident.discipline, func.count())
        .where(
            *open_incidents_where(tenant_id),
        )
        .group_by(Incident.discipline)
    )
    if date_from is not None:
        incidents_stmt = incidents_stmt.where(func.date(Incident.occurred_at) >= date_from)
    if date_to is not None:
        incidents_stmt = incidents_stmt.where(func.date(Incident.occurred_at) <= date_to)
    incidents, incidents_unmarked = await _grouped_counts(session, incidents_stmt)

    # Окно к просрочкам не применяется — они описывают состояние «на сегодня»,
    # как и у остальных разрезов.
    overdue = overdue_by_discipline(
        await attention_events(
            session=session,
            tenant_id=tenant_id,
            person_id=None,
            now=datetime.now(tz=timezone.utc),
        )
    )

    applicability = await collect_applicability(session, tenant_id)
    with_facts: list[Discipline] = []
    items: list[dict[str, Any]] = []
    for position, discipline in enumerate(Discipline):
        counted = discipline in ATTENTION_DISCIPLINES
        row: dict[str, Any] = {
            "id": discipline.value,
            "name": DISCIPLINE_TITLES[discipline],
            "incidents_open": incidents.get(discipline.value, 0),
            "overdue_items": overdue.get(discipline, 0) if counted else None,
        }
        row["total_issues"] = row["incidents_open"] + (row["overdue_items"] or 0)
        if not applicability.applies(discipline):
            if row["total_issues"] == 0:
                continue
            with_facts.append(discipline)
        items.append(row)
        row["_order"] = position
    if incidents_unmarked > 0:
        items.append(
            {
                "id": NO_DISCIPLINE_BUCKET_ID,
                "name": NO_DISCIPLINE_BUCKET_NAME,
                "incidents_open": incidents_unmarked,
                "overdue_items": None,
                "total_issues": incidents_unmarked,
                "_order": len(items),
            }
        )

    # Худшее сверху, при равенстве — порядок словаря, а не алфавит: «БДД»
    # впереди «Медосмотров» ничего не значит.
    items.sort(key=lambda r: (-r["total_issues"], r.pop("_order")))
    return {
        "dimension": "discipline",
        "items": items,
        "total": len(items),
        "not_applicable": describe_hidden(applicability, with_facts=with_facts),
    }


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
