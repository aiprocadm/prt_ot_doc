from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ClientPackageRun, Incident, Inspection, Person
from app.modules.client_portal.services import SafePortalPayloadService
from app.modules.projections.models import (
    ClientPortalReadModel,
    ContractorReadinessReadModel,
    DashboardKpiSnapshot,
    PackageReadModel,
    PersonComplianceReadModel,
    SearchIndexEntry,
    SiteSafetyReadModel,
)


class PackageProjectionService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def rebuild(self) -> int:
        return await ProjectionOrchestrator(self.session, self.tenant_id).rebuild_package_projection()


class PersonComplianceProjectionService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def rebuild(self) -> int:
        return await ProjectionOrchestrator(self.session, self.tenant_id).rebuild_person_projection()


class SiteSafetyProjectionService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def rebuild(self) -> int:
        persons_by_site = (
            await self.session.execute(
                select(Person.site_id, func.count(Person.id))
                .where(Person.tenant_id == self.tenant_id, Person.deleted_at.is_(None), Person.site_id.is_not(None))
                .group_by(Person.site_id)
            )
        ).all()
        incidents_by_site = (
            await self.session.execute(
                select(Incident.site_id, func.count(Incident.id)).where(Incident.tenant_id == self.tenant_id).group_by(Incident.site_id)
            )
        ).all()
        inspections_by_site = (
            await self.session.execute(
                select(Inspection.site_id, func.count(Inspection.id)).where(Inspection.tenant_id == self.tenant_id).group_by(Inspection.site_id)
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
                    select(SiteSafetyReadModel).where(SiteSafetyReadModel.tenant_id == self.tenant_id, SiteSafetyReadModel.site_id == site_id)
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
        rows = (await self.session.execute(select(ClientPackageRun).where(ClientPackageRun.tenant_id == self.tenant_id))).scalars().all()
        grouped: dict[str, int] = {}
        for run in rows:
            contractor_id = run.client_company_id
            if not contractor_id:
                continue
            grouped[contractor_id] = grouped.get(contractor_id, 0) + 1

        total = 0
        for contractor_id, packages_count in grouped.items():
            row = (
                await self.session.execute(
                    select(ContractorReadinessReadModel).where(
                        ContractorReadinessReadModel.tenant_id == self.tenant_id,
                        ContractorReadinessReadModel.contractor_id == contractor_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = ContractorReadinessReadModel(tenant_id=self.tenant_id, contractor_id=contractor_id)
                self.session.add(row)
            row.active_packages_count = packages_count
            row.readiness_status = "warning" if packages_count else "unknown"
            total += 1

        await self.session.commit()
        return total


class ClientPortalProjectionService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def rebuild(self) -> int:
        runs = (await self.session.execute(select(ClientPackageRun).where(ClientPackageRun.tenant_id == self.tenant_id))).scalars().all()
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
                    "internal_notes": (run.qc_report_json or {}).get("internal_notes") if run.qc_report_json else None,
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
        runs = (await self.session.execute(select(ClientPackageRun).where(ClientPackageRun.tenant_id == self.tenant_id))).scalars().all()
        count = 0
        for run in runs:
            row = (
                await self.session.execute(
                    select(PackageReadModel).where(PackageReadModel.tenant_id == self.tenant_id, PackageReadModel.package_id == run.id)
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
        persons = (await self.session.execute(select(Person).where(Person.tenant_id == self.tenant_id, Person.deleted_at.is_(None)))).scalars().all()
        count = 0
        for person in persons:
            row = (
                await self.session.execute(
                    select(PersonComplianceReadModel).where(PersonComplianceReadModel.tenant_id == self.tenant_id, PersonComplianceReadModel.person_id == person.id)
                )
            ).scalar_one_or_none()
            if row is None:
                row = PersonComplianceReadModel(tenant_id=self.tenant_id, person_id=person.id)
                self.session.add(row)
            row.company_id = person.company_id
            row.site_id = person.site_id
            row.readiness_status = "unknown"
            row.search_text = " ".join(filter(None, [person.last_name, person.first_name, person.middle_name]))
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
        persons = (await self.session.execute(select(Person).where(Person.tenant_id == self.tenant_id, Person.deleted_at.is_(None)))).scalars().all()
        count = 0
        for person in persons:
            title = " ".join(filter(None, [person.last_name, person.first_name, person.middle_name]))
            row = (
                await self.session.execute(
                    select(SearchIndexEntry).where(
                        SearchIndexEntry.tenant_id == self.tenant_id,
                        SearchIndexEntry.entity_type == "person",
                        SearchIndexEntry.entity_id == person.id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = SearchIndexEntry(tenant_id=self.tenant_id, entity_type="person", entity_id=person.id, title=title)
                self.session.add(row)
            row.title = title
            row.search_text = title
            row.route = f"/persons/{person.id}"
            count += 1
        await self.session.commit()
        return count

    async def rebuild_dashboard_snapshot(self, snapshot_date: date) -> DashboardKpiSnapshot:
        packages_total = int(await self.session.scalar(select(func.count()).select_from(PackageReadModel).where(PackageReadModel.tenant_id == self.tenant_id)) or 0)
        incidents_open = int(await self.session.scalar(select(func.count()).select_from(Incident).where(Incident.tenant_id == self.tenant_id)) or 0)
        inspections_open = int(await self.session.scalar(select(func.count()).select_from(Inspection).where(Inspection.tenant_id == self.tenant_id)) or 0)
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
            snapshot = DashboardKpiSnapshot(tenant_id=self.tenant_id, scope_type="tenant", scope_id=None, snapshot_date=snapshot_date)
            self.session.add(snapshot)
        snapshot.payload = {
            "packages_total": packages_total,
            "incidents_open": incidents_open,
            "inspections_open": inspections_open,
        }
        await self.session.commit()
        return snapshot
