from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Contract, Order
from app.models.models import (
    NPA,
    BriefingEntry,
    ClientPackageRun,
    Company,
    Incident,
    Inspection,
    InspectionStatus,
    Person,
    Prescription,
    Site,
    TrainingEnrollment,
)
from app.models.notifications import PlanTask
from app.modules.client_portal.services import SafePortalPayloadService
from app.modules.contractors.lifecycle import ReadinessStatus as ContractorReadinessStatus
from app.modules.contractors.models import ContractorEmployee, ContractorRegistry
from app.modules.projections.models import (
    ClientPortalReadModel,
    ContractorReadinessReadModel,
    DashboardKpiSnapshot,
    PackageReadModel,
    PersonComplianceReadModel,
    SearchIndexEntry,
    SiteSafetyReadModel,
)
from app.modules.workflow.models import WorkflowTask, WorkflowTaskStatus
from app.services.contractor_admission import evaluate_with_documents
from app.services.discipline_incidents import open_incidents_where


class PackageProjectionService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def rebuild(self) -> int:
        return await ProjectionOrchestrator(
            self.session, self.tenant_id
        ).rebuild_package_projection()


class PersonComplianceProjectionService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def rebuild(self) -> int:
        return await ProjectionOrchestrator(
            self.session, self.tenant_id
        ).rebuild_person_projection()


class SiteSafetyProjectionService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def rebuild(self) -> int:
        persons_by_site = (
            await self.session.execute(
                select(Person.site_id, func.count(Person.id))
                .where(
                    Person.tenant_id == self.tenant_id,
                    Person.deleted_at.is_(None),
                    Person.site_id.is_not(None),
                )
                .group_by(Person.site_id)
            )
        ).all()
        incidents_by_site = (
            await self.session.execute(
                select(Incident.site_id, func.count(Incident.id))
                .where(*open_incidents_where(self.tenant_id))
                .group_by(Incident.site_id)
            )
        ).all()
        inspections_by_site = (
            await self.session.execute(
                select(Inspection.site_id, func.count(Inspection.id))
                .where(
                    Inspection.tenant_id == self.tenant_id,
                    Inspection.deleted_at.is_(None),
                    Inspection.status.notin_(
                        [InspectionStatus.COMPLETED, InspectionStatus.CANCELLED]
                    ),
                )
                .group_by(Inspection.site_id)
            )
        ).all()

        person_map = {site_id: int(cnt) for site_id, cnt in persons_by_site if site_id}
        incident_map = {site_id: int(cnt) for site_id, cnt in incidents_by_site if site_id}
        inspection_map = {site_id: int(cnt) for site_id, cnt in inspections_by_site if site_id}
        all_sites = set(person_map) | set(incident_map) | set(inspection_map)

        total = 0
        for site_id in all_sites:
            row = (
                await self.session.execute(
                    select(SiteSafetyReadModel).where(
                        SiteSafetyReadModel.tenant_id == self.tenant_id,
                        SiteSafetyReadModel.site_id == site_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = SiteSafetyReadModel(tenant_id=self.tenant_id, site_id=site_id)
                self.session.add(row)
            row.active_people_count = person_map.get(site_id, 0)
            row.open_incidents_count = incident_map.get(site_id, 0)
            row.open_inspections_count = inspection_map.get(site_id, 0)
            row.readiness_status = "warning" if row.open_incidents_count else "ready"
            row.search_text = f"{site_id} {row.readiness_status}"
            total += 1

        await self.session.commit()
        return total


class ContractorReadinessProjectionService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def rebuild(self) -> int:
        # The authoritative contractor set is the registry — not package runs.
        # ClientPackageRun is keyed by *company* id, a different id space from the
        # registry id that ContractorEmployee.contractor_id references, so we must
        # iterate registries and join packages through ContractorRegistry.company_id.
        registries = (
            (
                await self.session.execute(
                    select(ContractorRegistry).where(
                        ContractorRegistry.tenant_id == self.tenant_id,
                        ContractorRegistry.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )

        # Active package runs counted per client company (for the company→contractor join below).
        package_runs = (
            (
                await self.session.execute(
                    select(ClientPackageRun).where(ClientPackageRun.tenant_id == self.tenant_id)
                )
            )
            .scalars()
            .all()
        )
        packages_by_company: dict[str, int] = {}
        for run in package_runs:
            if not run.client_company_id:
                continue
            packages_by_company[run.client_company_id] = (
                packages_by_company.get(run.client_company_id, 0) + 1
            )

        # Non-deleted employees grouped by contractor (registry) id.
        employees = (
            (
                await self.session.execute(
                    select(ContractorEmployee).where(
                        ContractorEmployee.tenant_id == self.tenant_id,
                        ContractorEmployee.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        employees_by_contractor: dict[str, list[ContractorEmployee]] = {}
        for emp in employees:
            employees_by_contractor.setdefault(emp.contractor_id, []).append(emp)

        # Doc-aware verdicts computed once for the whole tenant (2 extra queries total),
        # then regrouped per contractor below.
        all_verdicts = await evaluate_with_documents(self.session, employees=list(employees))
        verdict_by_emp = {v.employee_id: v for v in all_verdicts}

        total = 0
        for registry in registries:
            contractor_id = registry.id
            contractor_employees = employees_by_contractor.get(contractor_id, [])
            verdicts = [verdict_by_emp[e.id] for e in contractor_employees]

            workers_total = len(verdicts)
            workers_ready = sum(
                1 for v in verdicts if v.status is ContractorReadinessStatus.ALLOWED
            )
            workers_blocked = sum(
                1 for v in verdicts if v.status is ContractorReadinessStatus.BLOCKED
            )
            # "training" in violations covers overdue / expired / absent last_training_at —
            # not only the literally-missing sub-case the column name might suggest.
            missing_training_count = sum(1 for v in verdicts if "training" in v.violations)
            overdue_items_count = sum(len(v.violations) for v in verdicts)

            if workers_blocked > 0:
                readiness_status = "blocked"
            elif any(v.status is ContractorReadinessStatus.WARNING for v in verdicts):
                readiness_status = "warning"
            elif workers_total > 0:
                readiness_status = "ready"
            else:
                readiness_status = "unknown"

            # Per-contractor SELECT upsert (N+1) — consistent with the sibling
            # projection services; acceptable for the daily batch rebuild.
            row = (
                await self.session.execute(
                    select(ContractorReadinessReadModel).where(
                        ContractorReadinessReadModel.tenant_id == self.tenant_id,
                        ContractorReadinessReadModel.contractor_id == contractor_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = ContractorReadinessReadModel(
                    tenant_id=self.tenant_id, contractor_id=contractor_id
                )
                self.session.add(row)

            row.company_id = registry.company_id
            row.workers_total = workers_total
            row.workers_ready = workers_ready
            row.workers_blocked = workers_blocked
            row.missing_docs_count = sum(
                1 for v in verdicts for viol in v.violations if viol.startswith("document:")
            )
            row.missing_training_count = missing_training_count
            row.overdue_items_count = overdue_items_count
            row.active_packages_count = (
                packages_by_company.get(registry.company_id, 0) if registry.company_id else 0
            )
            row.readiness_status = readiness_status
            total += 1

        await self.session.commit()
        return total


class ClientPortalProjectionService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def rebuild(self) -> int:
        runs = (
            (
                await self.session.execute(
                    select(ClientPackageRun).where(ClientPackageRun.tenant_id == self.tenant_id)
                )
            )
            .scalars()
            .all()
        )
        count = 0
        for run in runs:
            row = (
                await self.session.execute(
                    select(ClientPortalReadModel).where(
                        ClientPortalReadModel.tenant_id == self.tenant_id,
                        ClientPortalReadModel.package_id == run.id,
                        ClientPortalReadModel.item_type == "package",
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = ClientPortalReadModel(
                    tenant_id=self.tenant_id,
                    package_id=run.id,
                    item_type="package",
                    title=f"Package {run.id[:8]}",
                    status=str(run.status),
                )
                self.session.add(row)
            row.client_company_id = run.client_company_id
            row.status = str(run.status)
            row.progress_percent = 0
            row.last_event_at = run.updated_at
            row.safe_payload = SafePortalPayloadService.sanitize(
                {
                    "progress_percent": 0,
                    "status": str(run.status),
                    "internal_notes": (
                        (run.qc_report_json or {}).get("internal_notes")
                        if run.qc_report_json
                        else None
                    ),
                }
            )
            count += 1
        await self.session.commit()
        return count


class ProjectionOrchestrator:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def rebuild_package_projection(self) -> int:
        runs = (
            (
                await self.session.execute(
                    select(ClientPackageRun).where(ClientPackageRun.tenant_id == self.tenant_id)
                )
            )
            .scalars()
            .all()
        )
        count = 0
        for run in runs:
            row = (
                await self.session.execute(
                    select(PackageReadModel).where(
                        PackageReadModel.tenant_id == self.tenant_id,
                        PackageReadModel.package_id == run.id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = PackageReadModel(tenant_id=self.tenant_id, package_id=run.id)
                self.session.add(row)
            row.package_code = run.id[:8]
            row.status = str(run.status)
            row.client_company_id = run.client_company_id
            row.progress_percent = float(run.progress_percent or 0)
            row.last_event_at = run.updated_at
            row.search_text = f"{row.package_code} {row.status}"
            count += 1
        await self.session.commit()
        return count

    async def rebuild_person_projection(self) -> int:
        persons = (
            (
                await self.session.execute(
                    select(Person).where(
                        Person.tenant_id == self.tenant_id, Person.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        # Per-person overdue counts, grouped once to avoid N+1. Decision (documented
        # in the review sweep #16): "overdue" = a lapsed validity — a training
        # enrolment whose certificate expiry (expires_at) or a briefing whose
        # valid_until is in the past. readiness_status is "blocked" when the person has
        # any overdue item, else "ready".
        now = datetime.now(tz=timezone.utc)
        overdue_trainings_by_person = {
            pid: int(cnt)
            for pid, cnt in (
                await self.session.execute(
                    select(TrainingEnrollment.person_id, func.count())
                    .where(
                        TrainingEnrollment.tenant_id == self.tenant_id,
                        TrainingEnrollment.deleted_at.is_(None),
                        TrainingEnrollment.expires_at.is_not(None),
                        TrainingEnrollment.expires_at < now,
                    )
                    .group_by(TrainingEnrollment.person_id)
                )
            ).all()
        }
        overdue_briefings_by_person = {
            pid: int(cnt)
            for pid, cnt in (
                await self.session.execute(
                    select(BriefingEntry.person_id, func.count())
                    .where(
                        BriefingEntry.tenant_id == self.tenant_id,
                        BriefingEntry.deleted_at.is_(None),
                        BriefingEntry.person_id.is_not(None),
                        BriefingEntry.valid_until.is_not(None),
                        BriefingEntry.valid_until < now,
                    )
                    .group_by(BriefingEntry.person_id)
                )
            ).all()
        }
        count = 0
        for person in persons:
            row = (
                await self.session.execute(
                    select(PersonComplianceReadModel).where(
                        PersonComplianceReadModel.tenant_id == self.tenant_id,
                        PersonComplianceReadModel.person_id == person.id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = PersonComplianceReadModel(tenant_id=self.tenant_id, person_id=person.id)
                self.session.add(row)
            row.company_id = person.company_id
            # Person has no site_id column (ARCH-2 decomposition); guard defensively so
            # the projection can't AttributeError on it.
            row.site_id = getattr(person, "site_id", None)
            overdue_trainings = overdue_trainings_by_person.get(person.id, 0)
            overdue_briefings = overdue_briefings_by_person.get(person.id, 0)
            row.overdue_trainings = overdue_trainings
            row.overdue_briefings = overdue_briefings
            row.readiness_status = (
                "blocked" if (overdue_trainings + overdue_briefings) > 0 else "ready"
            )
            row.search_text = " ".join(
                filter(None, [person.last_name, person.first_name, person.middle_name])
            )
            count += 1
        await self.session.commit()
        return count

    async def rebuild_person_compliance_projection(self) -> int:
        return await self.rebuild_person_projection()

    async def rebuild_site_safety_projection(self) -> int:
        return await SiteSafetyProjectionService(self.session, self.tenant_id).rebuild()

    async def rebuild_contractor_readiness_projection(self) -> int:
        return await ContractorReadinessProjectionService(self.session, self.tenant_id).rebuild()

    async def rebuild_client_portal_projection(self) -> int:
        return await ClientPortalProjectionService(self.session, self.tenant_id).rebuild()

    async def rebuild_search_index(self) -> int:
        persons = (
            (
                await self.session.execute(
                    select(Person).where(
                        Person.tenant_id == self.tenant_id, Person.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        companies = (
            (
                await self.session.execute(
                    select(Company).where(
                        Company.tenant_id == self.tenant_id, Company.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        sites = (
            (
                await self.session.execute(
                    select(Site).where(Site.tenant_id == self.tenant_id, Site.deleted_at.is_(None))
                )
            )
            .scalars()
            .all()
        )
        incidents = (
            (
                await self.session.execute(
                    select(Incident).where(
                        Incident.tenant_id == self.tenant_id, Incident.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        inspections = (
            (
                await self.session.execute(
                    select(Inspection).where(
                        Inspection.tenant_id == self.tenant_id, Inspection.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        prescriptions = (
            (
                await self.session.execute(
                    select(Prescription).where(
                        Prescription.tenant_id == self.tenant_id, Prescription.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        npa_items = (
            (await self.session.execute(select(NPA).where(NPA.tenant_id == self.tenant_id)))
            .scalars()
            .all()
        )
        contracts = (
            (
                await self.session.execute(
                    select(Contract).where(
                        Contract.tenant_id == self.tenant_id, Contract.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        orders = (
            (
                await self.session.execute(
                    select(Order).where(
                        Order.tenant_id == self.tenant_id, Order.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        plan_tasks = (
            (
                await self.session.execute(
                    select(PlanTask).where(
                        PlanTask.tenant_id == self.tenant_id, PlanTask.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        workflow_tasks = (
            (
                await self.session.execute(
                    select(WorkflowTask).where(
                        WorkflowTask.tenant_id == self.tenant_id,
                        WorkflowTask.deleted_at.is_(None),
                        WorkflowTask.status == WorkflowTaskStatus.OPEN,
                    )
                )
            )
            .scalars()
            .all()
        )
        count = 0

        async def upsert_entry(
            *,
            entity_type: str,
            entity_id: str,
            title: str,
            subtitle: str | None = None,
            status: str | None = None,
            route: str | None = None,
            preview_payload: dict | None = None,
            tags_json: dict | None = None,
            search_text: str | None = None,
        ) -> None:
            nonlocal count
            row = (
                await self.session.execute(
                    select(SearchIndexEntry).where(
                        SearchIndexEntry.tenant_id == self.tenant_id,
                        SearchIndexEntry.entity_type == entity_type,
                        SearchIndexEntry.entity_id == entity_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = SearchIndexEntry(
                    tenant_id=self.tenant_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    title=title,
                )
                self.session.add(row)
            row.title = title
            row.subtitle = subtitle
            row.status = status
            row.route = route
            row.preview_payload = preview_payload or {}
            row.tags_json = tags_json or {}
            row.search_text = search_text or " ".join(
                part for part in [title, subtitle or "", str(preview_payload or "")] if part
            )
            count += 1

        for person in persons:
            title = " ".join(
                filter(None, [person.last_name, person.first_name, person.middle_name])
            )
            await upsert_entry(
                entity_type="person",
                entity_id=person.id,
                title=title,
                subtitle=person.personnel_number,
                status=(
                    person.employment_status.value
                    if hasattr(person.employment_status, "value")
                    else str(person.employment_status)
                ),
                route=f"/persons/{person.id}",
                preview_payload={"email": person.email, "phone": person.phone},
                tags_json={
                    "company_id": person.company_id,
                    "site_id": getattr(person, "site_id", None),
                },
                search_text=" ".join(
                    filter(
                        None,
                        [
                            title,
                            person.personnel_number or "",
                            person.email or "",
                            person.phone or "",
                        ],
                    )
                ),
            )
        for company in companies:
            await upsert_entry(
                entity_type="company",
                entity_id=company.id,
                title=company.name,
                subtitle=company.inn or company.ogrn,
                route=f"/companies/{company.id}",
                preview_payload={
                    "director": company.director,
                    "activity_type": company.activity_type,
                },
                search_text=" ".join(
                    filter(
                        None,
                        [
                            company.name,
                            company.inn or "",
                            company.ogrn or "",
                            company.contact_email or "",
                        ],
                    )
                ),
            )
        for site in sites:
            await upsert_entry(
                entity_type="site",
                entity_id=site.id,
                title=site.name,
                subtitle=site.address,
                status=site.hazard_class,
                route=f"/sites/{site.id}",
                tags_json={"company_id": site.company_id},
                preview_payload={"site_type": site.site_type, "contact_name": site.contact_name},
            )
        for incident in incidents:
            await upsert_entry(
                entity_type="incident",
                entity_id=incident.id,
                title=incident.title,
                subtitle=incident.location_description,
                status=(
                    incident.status.value
                    if hasattr(incident.status, "value")
                    else str(incident.status)
                ),
                route=f"/incidents?id={incident.id}",
                tags_json={"company_id": incident.company_id, "site_id": incident.site_id},
                preview_payload={
                    "severity": str(
                        incident.severity.value
                        if hasattr(incident.severity, "value")
                        else incident.severity
                    )
                },
                search_text=" ".join(
                    filter(
                        None,
                        [
                            incident.title,
                            incident.description or "",
                            incident.location_description or "",
                        ],
                    )
                ),
            )
        for inspection in inspections:
            await upsert_entry(
                entity_type="inspection",
                entity_id=inspection.id,
                title=inspection.authority,
                subtitle=inspection.purpose,
                status=(
                    inspection.status.value
                    if hasattr(inspection.status, "value")
                    else str(inspection.status)
                ),
                route=f"/inspections?id={inspection.id}",
                tags_json={"company_id": inspection.company_id, "site_id": inspection.site_id},
                preview_payload={
                    "inspection_type": str(
                        inspection.inspection_type.value
                        if hasattr(inspection.inspection_type, "value")
                        else inspection.inspection_type
                    )
                },
            )
        for prescription in prescriptions:
            await upsert_entry(
                entity_type="prescription",
                entity_id=prescription.id,
                title=(prescription.description or "")[:120]
                or f"Prescription {prescription.id[:8]}",
                subtitle=prescription.description,
                status=(
                    prescription.status.value
                    if hasattr(prescription.status, "value")
                    else str(prescription.status)
                ),
                route=f"/prescriptions?id={prescription.id}",
                preview_payload={
                    "inspection_id": prescription.inspection_id,
                    "incident_id": prescription.incident_id,
                },
                search_text=prescription.description,
            )
        for item in npa_items:
            await upsert_entry(
                entity_type="npa",
                entity_id=item.id,
                title=item.code,
                subtitle=item.title,
                status=item.status.value if hasattr(item.status, "value") else str(item.status),
                route=f"/npa?selected={item.id}",
                preview_payload={
                    "edition_date": item.edition_date.isoformat() if item.edition_date else None
                },
                search_text=f"{item.code} {item.title}",
            )
        for contract in contracts:
            await upsert_entry(
                entity_type="contract",
                entity_id=contract.id,
                title=contract.title,
                subtitle=contract.contract_number or contract.counterparty_name,
                status=(
                    contract.status.value
                    if hasattr(contract.status, "value")
                    else str(contract.status)
                ),
                route=f"/contracts/{contract.id}",
                tags_json={"company_id": contract.company_id, "site_id": contract.site_id},
                search_text=" ".join(
                    filter(
                        None,
                        [
                            contract.title,
                            contract.contract_number or "",
                            contract.counterparty_name,
                        ],
                    )
                ),
            )
        for order in orders:
            await upsert_entry(
                entity_type="order",
                entity_id=order.id,
                title=order.order_number,
                subtitle=f"Contract {order.contract_id}",
                status=order.status.value if hasattr(order.status, "value") else str(order.status),
                route=f"/orders/{order.id}",
                preview_payload={"contract_id": order.contract_id},
                search_text=f"{order.order_number} {order.contract_id}",
            )
        for task in plan_tasks:
            await upsert_entry(
                entity_type="task",
                entity_id=task.id,
                title=task.title,
                subtitle=task.description,
                status=task.status.value if hasattr(task.status, "value") else str(task.status),
                route=f"/tasks?task={task.id}",
                preview_payload={"entity_type": task.entity_type, "entity_id": task.entity_id},
                search_text=" ".join(
                    filter(
                        None, [task.title, task.description or "", task.entity_type, task.entity_id]
                    )
                ),
            )
        for task in workflow_tasks:
            await upsert_entry(
                entity_type="workflow_task",
                entity_id=task.id,
                title=task.title,
                subtitle=task.node_id,
                status=task.status.value if hasattr(task.status, "value") else str(task.status),
                route=f"/workflow?task={task.id}",
                preview_payload={
                    "instance_id": task.instance_id,
                    "assignee_role_code": task.assignee_role_code,
                },
                search_text=" ".join(
                    filter(
                        None,
                        [
                            task.title,
                            task.node_id,
                            task.assignee_role_code or "",
                            task.assignee_user_id or "",
                        ],
                    )
                ),
            )
        await self.session.commit()
        return count

    async def rebuild_dashboard_snapshot(self, snapshot_date: date) -> DashboardKpiSnapshot:
        packages_total = int(
            await self.session.scalar(
                select(func.count())
                .select_from(PackageReadModel)
                .where(PackageReadModel.tenant_id == self.tenant_id)
            )
            or 0
        )
        # Snapshot the same KPI values the trend series reads (from the read models),
        # so a daily snapshot captures the dashboard figures and trend_series can read
        # this history instead of re-running a flat current query (#29). Reading the
        # SiteSafety read model also inherits its correct open-count semantics.
        incidents_open, inspections_open = (
            await self.session.execute(
                select(
                    func.coalesce(func.sum(SiteSafetyReadModel.open_incidents_count), 0),
                    func.coalesce(func.sum(SiteSafetyReadModel.open_inspections_count), 0),
                ).where(SiteSafetyReadModel.tenant_id == self.tenant_id)
            )
        ).one()
        overdue_trainings, overdue_briefings = (
            await self.session.execute(
                select(
                    func.coalesce(func.sum(PersonComplianceReadModel.overdue_trainings), 0),
                    func.coalesce(func.sum(PersonComplianceReadModel.overdue_briefings), 0),
                ).where(PersonComplianceReadModel.tenant_id == self.tenant_id)
            )
        ).one()
        contractors_active = int(
            await self.session.scalar(
                select(
                    func.coalesce(func.sum(ContractorReadinessReadModel.active_packages_count), 0)
                ).where(ContractorReadinessReadModel.tenant_id == self.tenant_id)
            )
            or 0
        )
        snapshot = (
            await self.session.execute(
                select(DashboardKpiSnapshot).where(
                    DashboardKpiSnapshot.tenant_id == self.tenant_id,
                    DashboardKpiSnapshot.scope_type == "tenant",
                    DashboardKpiSnapshot.scope_id.is_(None),
                    DashboardKpiSnapshot.snapshot_date == snapshot_date,
                )
            )
        ).scalar_one_or_none()
        if snapshot is None:
            snapshot = DashboardKpiSnapshot(
                tenant_id=self.tenant_id,
                scope_type="tenant",
                scope_id=None,
                snapshot_date=snapshot_date,
            )
            self.session.add(snapshot)
        snapshot.payload = {
            "packages_total": packages_total,
            "incidents_open": int(incidents_open or 0),
            "inspections_open": int(inspections_open or 0),
            "overdue_trainings": int(overdue_trainings or 0),
            "overdue_compliance": int((overdue_trainings or 0) + (overdue_briefings or 0)),
            "contractors": int(contractors_active or 0),
        }
        await self.session.commit()
        return snapshot
