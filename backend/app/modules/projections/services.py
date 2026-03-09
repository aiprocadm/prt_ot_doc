from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ClientPackageRun, Incident, Inspection, Person
from app.modules.projections.models import DashboardKpiSnapshot, PackageReadModel, PersonComplianceReadModel, SearchIndexEntry


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
