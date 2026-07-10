"""CRUD + run-оркестрация report definitions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_builder import ReportDefinition
from app.modules.export_center.service import ExportCenterService
from app.modules.projections.models import ExportJob
from app.modules.report_builder.engine import validate_config

__all__ = [
    "ReportDefinitionNotFound",
    "ReportNameConflict",
    "SystemDefinitionImmutable",
    "ReportBuilderService",
]


class ReportDefinitionNotFound(Exception):
    pass


class ReportNameConflict(Exception):
    pass


class SystemDefinitionImmutable(Exception):
    pass


_UPDATABLE_FIELDS = ("name", "description", "dataset_code", "config_json")


class ReportBuilderService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def _base_stmt(self):
        return select(ReportDefinition).where(
            ReportDefinition.tenant_id == self.tenant_id,
            ReportDefinition.deleted_at.is_(None),
        )

    async def list_definitions(
        self, *, limit: int, offset: int
    ) -> tuple[list[ReportDefinition], int]:
        stmt = self._base_stmt()
        total = int(
            await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )
        rows = list(
            (
                await self.session.execute(
                    stmt.order_by(
                        ReportDefinition.is_system.desc(), ReportDefinition.name.asc()
                    )
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return rows, total

    async def get_definition(self, definition_id: str) -> ReportDefinition:
        row = await self.session.scalar(
            self._base_stmt().where(ReportDefinition.id == definition_id)
        )
        if row is None:
            raise ReportDefinitionNotFound(definition_id)
        return row

    async def create_definition(
        self,
        *,
        name: str,
        description: str | None,
        dataset_code: str,
        config_json: dict[str, Any],
    ) -> ReportDefinition:
        validate_config(dataset_code, config_json)  # ReportConfigError → 422 на роуте
        record = ReportDefinition(
            tenant_id=self.tenant_id,
            name=name,
            description=description,
            dataset_code=dataset_code,
            config_json=config_json,
        )
        self.session.add(record)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ReportNameConflict(name) from exc
        return record

    async def update_definition(
        self, definition: ReportDefinition, payload: dict[str, Any]
    ) -> ReportDefinition:
        if definition.is_system:
            raise SystemDefinitionImmutable(definition.id)
        fields = {k: v for k, v in payload.items() if k in _UPDATABLE_FIELDS}
        dataset_code = fields.get("dataset_code", definition.dataset_code)
        config_json = fields.get("config_json", definition.config_json)
        validate_config(dataset_code, config_json)
        for key, value in fields.items():
            setattr(definition, key, value)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ReportNameConflict(str(fields.get("name"))) from exc
        return definition

    async def soft_delete_definition(self, definition: ReportDefinition) -> None:
        if definition.is_system:
            raise SystemDefinitionImmutable(definition.id)
        definition.deleted_at = datetime.now(tz=timezone.utc)
        await self.session.flush()

    async def run_definition(self, definition: ReportDefinition, *, fmt: str) -> ExportJob:
        """Создаёт ExportJob(export_type="report") и ставит celery-материализатор.
        Скачивание/статус — существующие /exports/{id} и /exports/{id}/download-link."""
        job = await ExportCenterService(self.session, self.tenant_id).create_job(
            export_type="report",
            dataset_code=definition.dataset_code,
            scope_json={"definition_id": definition.id, "format": fmt},
            filters_json=dict(definition.config_json or {}),
            idempotency_key=None,
        )
        from app.celery.tasks.report_export_job import report_export_job

        report_export_job.delay(job_id=job.id, tenant_id=self.tenant_id)
        return job
