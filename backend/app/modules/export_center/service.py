from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.modules.projections.models import ExportJob, ExportSchedule, KpiDefinition
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class ExportCenterService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def create_job(
        self,
        *,
        export_type: str,
        scope_json: dict[str, Any],
        filters_json: dict[str, Any],
        idempotency_key: str | None,
        dataset_code: str | None = None,
        schema_version: str = "v1",
        anonymized: bool = False,
        target_type: str = "file",
        target_config: dict[str, Any] | None = None,
    ) -> ExportJob:
        if idempotency_key:
            existing = (
                await self.session.execute(
                    select(ExportJob).where(
                        ExportJob.tenant_id == self.tenant_id,
                        ExportJob.export_type == export_type,
                        ExportJob.scope_json == scope_json,
                        ExportJob.filters_json == filters_json,
                        ExportJob.status.in_(["queued", "running", "done"]),
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing

        job = ExportJob(
            tenant_id=self.tenant_id,
            export_type=export_type,
            dataset_code=dataset_code,
            schema_version=schema_version,
            anonymized=anonymized,
            target_type=target_type,
            target_config=target_config or {},
            scope_json=scope_json,
            filters_json=filters_json,
            status="queued",
            progress_percent=0,
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def record_delivery(self, job: ExportJob, *, status: str, payload: dict[str, Any]) -> ExportJob:
        history = list(job.delivery_history_json or [])
        history.append({"status": status, "payload": payload, "at": datetime.now(tz=timezone.utc).isoformat()})
        job.delivery_history_json = history
        job.progress_percent = 100 if status == "delivered" else job.progress_percent
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def create_schedule(self, *, name: str, dataset_code: str, cron_expr: str, filters_json: dict[str, Any], anonymized: bool, target_type: str, target_config: dict[str, Any]) -> ExportSchedule:
        return await self.create_schedule_with_schema(
            name=name,
            dataset_code=dataset_code,
            schema_version="v1",
            cron_expr=cron_expr,
            filters_json=filters_json,
            anonymized=anonymized,
            target_type=target_type,
            target_config=target_config,
        )

    async def create_schedule_with_schema(
        self,
        *,
        name: str,
        dataset_code: str,
        schema_version: str,
        cron_expr: str,
        filters_json: dict[str, Any],
        anonymized: bool,
        target_type: str,
        target_config: dict[str, Any],
    ) -> ExportSchedule:
        item = ExportSchedule(
            tenant_id=self.tenant_id,
            name=name,
            dataset_code=dataset_code,
            schema_version=schema_version,
            cron_expr=cron_expr,
            filters_json=filters_json,
            anonymized=anonymized,
            target_type=target_type,
            target_config=target_config,
        )
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def create_kpi_definition(self, *, code: str, name: str, dataset_code: str, formula_json: dict[str, Any], threshold_json: dict[str, Any], locale_labels: dict[str, Any]) -> KpiDefinition:
        item = KpiDefinition(
            tenant_id=self.tenant_id,
            code=code,
            name=name,
            dataset_code=dataset_code,
            formula_json=formula_json,
            threshold_json=threshold_json,
            locale_labels=locale_labels,
        )
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    @staticmethod
    def dataset_catalog() -> list[dict[str, Any]]:
        return [
            {"code": "employees_training", "schema_version": "v1", "targets": ["file", "webhook", "dwh"], "anonymization_profiles": ["none", "basic"]},
            {"code": "risks", "schema_version": "v1", "targets": ["file", "webhook", "dwh"], "anonymization_profiles": ["none", "basic"]},
            {"code": "incidents", "schema_version": "v1", "targets": ["file", "webhook", "dwh"], "anonymization_profiles": ["none", "basic"]},
            {"code": "inspections_prescriptions", "schema_version": "v1", "targets": ["file", "webhook", "dwh"], "anonymization_profiles": ["none", "basic"]},
            {"code": "documents_edo", "schema_version": "v1", "targets": ["file", "webhook", "dwh"], "anonymization_profiles": ["none", "basic"]},
            {"code": "ppe_warehouse", "schema_version": "v1", "targets": ["file", "webhook", "dwh"], "anonymization_profiles": ["none", "basic"]},
            {"code": "billing_usage", "schema_version": "v1", "targets": ["file", "webhook", "dwh"], "anonymization_profiles": ["none", "tenant_only"]},
            {"code": "workflow_tasks", "schema_version": "v1", "targets": ["file", "webhook", "dwh"], "anonymization_profiles": ["none", "basic"]},
        ]

    async def run_schedule_now(self, schedule: ExportSchedule) -> ExportJob:
        return await self.create_job(
            export_type="analytics",
            dataset_code=schedule.dataset_code,
            schema_version=schedule.schema_version,
            anonymized=schedule.anonymized,
            target_type=schedule.target_type,
            target_config=schedule.target_config or {},
            scope_json={"schedule_id": schedule.id, "trigger": "manual"},
            filters_json=schedule.filters_json or {},
            idempotency_key=None,
        )
