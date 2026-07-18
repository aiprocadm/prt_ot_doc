"""Domain services for incident investigations and regulatory inspections."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File
from app.models.models import (
    Company,
    DocumentPack,
    Incident,
    IncidentLog,
    IncidentPerson,
    IncidentPersonRole,
    IncidentSeverity,
    IncidentStage,
    IncidentStatus,
    IncidentType,
    Inspection,
    InspectionResult,
    InspectionStatus,
    InspectionType,
    Person,
    Site,
)


async def _get_company(session: AsyncSession, tenant_id: str, company_id: str) -> Company:
    stmt = select(Company).where(
        Company.id == company_id, Company.tenant_id == tenant_id, Company.deleted_at.is_(None)
    )
    company = (await session.execute(stmt)).scalar_one_or_none()
    if company is None:
        raise ValueError("Company not found")
    return company


async def _get_site(session: AsyncSession, tenant_id: str, site_id: str) -> Site:
    stmt = select(Site).where(
        Site.id == site_id, Site.tenant_id == tenant_id, Site.deleted_at.is_(None)
    )
    site = (await session.execute(stmt)).scalar_one_or_none()
    if site is None:
        raise ValueError("Site not found")
    return site


async def _get_pack(session: AsyncSession, tenant_id: str, pack_id: str) -> DocumentPack:
    stmt = select(DocumentPack).where(
        DocumentPack.id == pack_id,
        DocumentPack.tenant_id == tenant_id,
        DocumentPack.deleted_at.is_(None),
    )
    pack = (await session.execute(stmt)).scalar_one_or_none()
    if pack is None:
        raise ValueError("Document pack not found")
    return pack


async def _get_persons(
    session: AsyncSession, tenant_id: str, person_ids: Sequence[str], company_id: str | None = None
) -> list[Person]:
    if not person_ids:
        return []
    stmt = select(Person).where(
        Person.id.in_(person_ids), Person.tenant_id == tenant_id, Person.deleted_at.is_(None)
    )
    persons = list((await session.execute(stmt)).scalars().all())
    missing = set(person_ids) - {person.id for person in persons}
    if missing:
        raise ValueError(f"Persons not found: {', '.join(sorted(missing))}")
    if company_id:
        invalid = [person.id for person in persons if person.company_id != company_id]
        if invalid:
            raise ValueError(f"Persons do not belong to company: {', '.join(sorted(invalid))}")
    return persons


async def _replace_victims(
    session: AsyncSession, *, tenant_id: str, incident: Incident, victim_ids: Sequence[str]
) -> None:
    existing_stmt = select(IncidentPerson).where(
        IncidentPerson.tenant_id == tenant_id,
        IncidentPerson.incident_id == incident.id,
        IncidentPerson.role == IncidentPersonRole.VICTIM,
    )
    existing_records = list((await session.execute(existing_stmt)).scalars().all())
    current_ids = {record.person_id for record in existing_records}
    desired_ids = set(victim_ids)

    for record in existing_records:
        if record.person_id not in desired_ids:
            await session.delete(record)

    new_ids = desired_ids - current_ids
    for person_id in new_ids:
        session.add(
            IncidentPerson(
                tenant_id=tenant_id,
                incident_id=incident.id,
                person_id=person_id,
                role=IncidentPersonRole.VICTIM,
            )
        )


async def register_incident(
    session: AsyncSession,
    *,
    tenant_id: str,
    title: str,
    company_id: str,
    site_id: str,
    occurred_at: datetime,
    incident_type: IncidentType,
    severity: IncidentSeverity,
    description: str | None = None,
    location_description: str | None = None,
    pack_id: str | None = None,
    victim_ids: Sequence[str] | None = None,
) -> Incident:
    company = await _get_company(session, tenant_id, company_id)
    site = await _get_site(session, tenant_id, site_id)
    if site.company_id != company.id:
        raise ValueError("Site does not belong to the specified company")

    pack = None
    if pack_id:
        pack = await _get_pack(session, tenant_id, pack_id)

    victims = await _get_persons(session, tenant_id, victim_ids or [], company_id=company.id)

    incident = Incident(
        tenant_id=tenant_id,
        title=title,
        company_id=company.id,
        site_id=site.id,
        occurred_at=occurred_at,
        incident_type=incident_type,
        severity=severity,
        description=description,
        location_description=location_description,
        pack_id=pack.id if pack else None,
        status=IncidentStatus.REPORTED,
        investigation_stage=IncidentStage.REGISTRATION,
    )
    session.add(incident)
    await session.flush()
    await _replace_victims(
        session, tenant_id=tenant_id, incident=incident, victim_ids=[p.id for p in victims]
    )
    return incident


async def update_incident(
    session: AsyncSession,
    *,
    tenant_id: str,
    incident: Incident,
    updates: dict[str, object],
    victim_ids: Sequence[str] | None = None,
) -> Incident:
    if "company_id" in updates:
        company = await _get_company(session, tenant_id, str(updates["company_id"]))
        incident.company_id = company.id
    if "site_id" in updates:
        site = await _get_site(session, tenant_id, str(updates["site_id"]))
        if site.company_id != incident.company_id:
            raise ValueError("Site does not belong to the specified company")
        incident.site_id = site.id
    if "pack_id" in updates and updates["pack_id"] is not None:
        pack = await _get_pack(session, tenant_id, str(updates["pack_id"]))
        incident.pack_id = pack.id
    elif "pack_id" in updates and updates["pack_id"] is None:
        incident.pack_id = None

    if "status" in updates:
        current_status = incident.status
        target_status = updates["status"]
        current_val = getattr(current_status, "value", current_status)
        # Lifecycle (documented decision, review sweep #14): the open states advance in
        # order reported -> investigating -> corrective_actions -> closed (forward or
        # skip-ahead allowed, backward moves rejected); cancelled is reachable from any
        # open state; closed/cancelled are terminal (no change out of them).
        _order = {
            IncidentStatus.REPORTED: 0,
            IncidentStatus.INVESTIGATING: 1,
            IncidentStatus.ACTIONS: 2,
            IncidentStatus.CLOSED: 3,
        }
        if current_status in (IncidentStatus.CLOSED, IncidentStatus.CANCELLED):
            if target_status != current_status:
                raise ValueError(f"cannot change status of a {current_val} incident")
        elif target_status != current_status and target_status != IncidentStatus.CANCELLED:
            cur_rank = _order.get(current_status)
            tgt_rank = _order.get(target_status)
            if cur_rank is not None and tgt_rank is not None and tgt_rank < cur_rank:
                tgt_val = getattr(target_status, "value", target_status)
                raise ValueError(
                    f"invalid incident transition: {current_val} -> {tgt_val} (backward)"
                )

    for key in {
        "title",
        "description",
        "incident_type",
        "occurred_at",
        "severity",
        "status",
        "investigation_stage",
        "location_description",
    }:
        if key in updates:
            setattr(incident, key, updates[key])

    if victim_ids is not None:
        await _get_persons(session, tenant_id, victim_ids, company_id=incident.company_id)
        await _replace_victims(
            session, tenant_id=tenant_id, incident=incident, victim_ids=victim_ids
        )

    await session.flush()
    return incident


async def append_log_entry(
    session: AsyncSession,
    *,
    tenant_id: str,
    incident: Incident,
    message: str,
    stage: IncidentStage,
    status: IncidentStatus,
    author_id: str | None = None,
    metadata: dict | None = None,
) -> IncidentLog:
    record = IncidentLog(
        tenant_id=tenant_id,
        incident_id=incident.id,
        author_id=author_id,
        stage=stage,
        status=status,
        message=message,
        metadata_json=metadata or {},
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def register_inspection(
    session: AsyncSession,
    *,
    tenant_id: str,
    company_id: str,
    authority: str,
    site_id: str | None = None,
    inspection_type: InspectionType | None = None,
    responsible_id: str | None = None,
    recurrence_rule: str | None = None,
    purpose: str | None = None,
    scheduled_at: date | None = None,
    status: InspectionStatus = InspectionStatus.PLANNED,
    started_at: datetime | None = None,
) -> Inspection:
    company = await _get_company(session, tenant_id, company_id)
    site = None
    if site_id:
        site = await _get_site(session, tenant_id, site_id)
        if site.company_id != company.id:
            raise ValueError("Site does not belong to the specified company")

    record = Inspection(
        tenant_id=tenant_id,
        company_id=company.id,
        site_id=site.id if site else None,
        inspection_type=inspection_type or InspectionType.INTERNAL,
        responsible_id=responsible_id,
        recurrence_rule=recurrence_rule,
        authority=authority,
        purpose=purpose,
        scheduled_at=scheduled_at,
        status=status,
        started_at=started_at,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def update_inspection(
    session: AsyncSession,
    *,
    tenant_id: str,
    inspection: Inspection,
    updates: dict[str, object],
) -> Inspection:
    if "company_id" in updates:
        company = await _get_company(session, tenant_id, str(updates["company_id"]))
        inspection.company_id = company.id
    if "site_id" in updates:
        site_id = updates["site_id"]
        if site_id is None:
            inspection.site_id = None
        else:
            site = await _get_site(session, tenant_id, str(site_id))
            if site.company_id != inspection.company_id:
                raise ValueError("Site does not belong to the specified company")
            inspection.site_id = site.id

    for key in {
        "inspection_type",
        "responsible_id",
        "recurrence_rule",
        "authority",
        "purpose",
        "scheduled_at",
        "status",
        "started_at",
        "finished_at",
        "result_summary",
    }:
        if key in updates:
            setattr(inspection, key, updates[key])

    await session.flush()
    await session.refresh(inspection)
    return inspection


async def add_inspection_result(
    session: AsyncSession,
    *,
    tenant_id: str,
    inspection: Inspection,
    title: str,
    outcome: str | None = None,
    notes: str | None = None,
    issued_at: date | None = None,
    file_id: str | None = None,
) -> InspectionResult:
    file: File | None = None
    if file_id:
        stmt = select(File).where(
            File.id == file_id, File.tenant_id == tenant_id, File.deleted_at.is_(None)
        )
        file = (await session.execute(stmt)).scalar_one_or_none()
        if file is None:
            raise ValueError("File not found")

    result = InspectionResult(
        tenant_id=tenant_id,
        inspection_id=inspection.id,
        title=title,
        outcome=outcome,
        notes=notes,
        issued_at=issued_at or datetime.now(timezone.utc).date(),
        file_id=file.id if file else None,
    )
    session.add(result)
    await session.flush()
    await session.refresh(result)
    return result
