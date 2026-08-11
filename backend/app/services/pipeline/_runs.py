"""PipelineService run-lifecycle helpers (ARCH-4 slice 9 split)."""

from __future__ import annotations

from time import perf_counter
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.metrics import (
    Metrics,
    PipelineStage,
    PipelineType,
    StageResult,
    sanitize_label,
)
from app.db.session import rearm_session_tenant_context
from app.models.models import PipelineRun, PipelineRunStatus, Template, TemplateVersion


class RunLifecycleMixin:
    """Pending-run creation / idempotent lookup and error normalization."""

    if TYPE_CHECKING:
        # Контракт хост-класса (PipelineService): атрибуты и методы,
        # которыми пользуется миксин, — реализации в service.py и _preparation.py.
        metrics: Metrics

        def _prepare_parameters(
            self,
            *,
            session: AsyncSession,
            template: Template,
            template_version: TemplateVersion,
            context: dict[str, Any],
            replacements: dict[str, str] | None,
            header_text: str | None,
            footer_text: str | None,
            output_basename: str | None,
            tenant_id: str | None,
        ) -> tuple[str, str | None, dict[str, str], dict[str, Any]]: ...

        @staticmethod
        def _validate_idempotent_run(
            run: PipelineRun,
            *,
            template_id: str,
            template_version_id: str,
            payload: dict[str, Any],
        ) -> None: ...

    async def ensure_pending_run(
        self,
        session: AsyncSession,
        *,
        template: Template,
        template_version: TemplateVersion,
        context: dict[str, Any],
        replacements: dict[str, str] | None,
        header_text: str | None,
        footer_text: str | None,
        idempotency_key: str,
        output_basename: str | None,
        tenant_id: str | None = None,
    ) -> tuple[PipelineRun, bool]:
        """Ensure a ``PipelineRun`` exists without executing heavy work."""

        stage_start = perf_counter()
        self.metrics.record_pipeline_stage_start(
            pipeline=PipelineType.DOCUMENT,
            stage=PipelineStage.DATA_PERSISTED,
        )
        try:
            (
                tenant_identifier,
                _normalized_output_basename,
                _replacements_map,
                request_metadata,
            ) = self._prepare_parameters(
                session=session,
                template=template,
                template_version=template_version,
                context=context,
                replacements=replacements,
                header_text=header_text,
                footer_text=footer_text,
                output_basename=output_basename,
                tenant_id=tenant_id,
            )

            run, created = await self._get_or_create_pending_run(
                session,
                tenant_id=tenant_identifier,
                idempotency_key=idempotency_key,
                template_id=template.id,
                template_version_id=template_version.id,
                payload=context,
                defaults={"result_metadata": {"request": request_metadata}},
            )

            metadata = dict(run.result_metadata or {})
            existing_request = metadata.get("request")
            if existing_request and existing_request != request_metadata:
                raise ValueError("Idempotency key collision for different pipeline options")
            if not existing_request:
                metadata["request"] = request_metadata
            run.result_metadata = metadata

            if created:
                run.status = PipelineRunStatus.QUEUED
                run.outputs = None
                run.docx_storage_key = None
                run.pdf_storage_key = None
                run.result_s3_key = None
                run.error = None
                run.started_at = None
                run.finished_at = None

            await session.flush()
        except Exception as exc:
            self.metrics.record_pipeline_stage_end(
                pipeline=PipelineType.DOCUMENT,
                stage=PipelineStage.DATA_PERSISTED,
                result=StageResult.FAILED,
                seconds=perf_counter() - stage_start,
                error_class=exc.__class__.__name__,
            )
            raise

        self.metrics.record_pipeline_stage_end(
            pipeline=PipelineType.DOCUMENT,
            stage=PipelineStage.DATA_PERSISTED,
            result=StageResult.SUCCESS,
            seconds=perf_counter() - stage_start,
        )
        return run, created

    @staticmethod
    def _normalize_error_details(exc: Exception) -> tuple[str, str]:
        message = (str(exc) or exc.__class__.__name__).strip()
        sanitized = sanitize_label(message)
        lowered = message.lower()
        metrics_code = sanitized
        if "template version payload missing" in lowered:
            metrics_code = "template_not_uploaded"
        return sanitized, metrics_code

    async def _get_or_create_pending_run(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        idempotency_key: str,
        template_id: str,
        template_version_id: str,
        payload: dict[str, Any],
        defaults: dict[str, Any] | None = None,
    ) -> tuple[PipelineRun, bool]:
        """Fetch an existing document job or create a new pending record.

        Ensures idempotency by validating that any existing job registered under
        ``idempotency_key`` was created for the same template, template version,
        and payload. When a mismatch is detected we raise ``ValueError`` to make
        the conflict explicit for callers.
        """

        stmt = select(PipelineRun).where(
            PipelineRun.tenant_id == tenant_id,
            PipelineRun.idempotency_key == idempotency_key,
        )
        run = (await session.execute(stmt)).scalar_one_or_none()
        if run:
            self._validate_idempotent_run(
                run,
                template_id=template_id,
                template_version_id=template_version_id,
                payload=payload,
            )
            return run, False

        create_kwargs = {
            "tenant_id": tenant_id,
            "idempotency_key": idempotency_key,
            "status": PipelineRunStatus.QUEUED,
            "template_id": template_id,
            "template_version_id": template_version_id,
            "context": payload,
        }
        if defaults:
            create_kwargs.update(defaults)
        run = PipelineRun(**create_kwargs)
        session.add(run)
        try:
            await session.flush()
        except IntegrityError:
            # Deliberate full rollback: it ends the transaction so the winning request's
            # committed run becomes visible to the re-read below. It also clears the
            # transaction-local RLS GUCs (SEC-65) — re-arm before querying again.
            await session.rollback()
            await rearm_session_tenant_context(session)
            run = (await session.execute(stmt)).scalar_one()
            self._validate_idempotent_run(
                run,
                template_id=template_id,
                template_version_id=template_version_id,
                payload=payload,
            )
            return run, False
        return run, True
