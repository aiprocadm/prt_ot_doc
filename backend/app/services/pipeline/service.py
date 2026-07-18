"""PipelineService — template rendering + PDF conversion orchestration (ARCH-4 slice 9).

The god-class was decomposed into mixins (preparation/stamping/staging/run-lifecycle);
this module keeps the class assembly, ``__init__`` and the ``run`` orchestrator.
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.metrics import (
    Metrics,
    PipelineStage,
    PipelineType,
    StageResult,
    get_metrics,
    sanitize_label,
)
from app.core.tenant import get_current_tenant
from app.models.models import PipelineRun, PipelineRunStatus, Template, TemplateVersion
from app.modules.files.utils import build_dated_prefix
from app.services.docx import DocxService
from app.services.file_storage import FileStorageService
from app.services.pdf import (
    MINI_PDF_BYTES,
    PdfConversionError,
    PdfConversionResult,
    PdfConverter,
)
from app.services.pipeline._base import StampingUnavailableError
from app.services.pipeline._preparation import PreparationMixin
from app.services.pipeline._runs import RunLifecycleMixin
from app.services.pipeline._staging import StagingMixin
from app.services.pipeline._stamping import StampingMixin

__all__ = ["PipelineService", "StampingUnavailableError"]

logger = logging.getLogger(__name__)

DocumentJob = PipelineRun
DocumentJobStatus = PipelineRunStatus


class PipelineService(PreparationMixin, StampingMixin, StagingMixin, RunLifecycleMixin):
    """Coordinate template rendering and PDF conversion for document jobs."""

    DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    def __init__(
        self,
        storage: FileStorageService | None = None,
        pdf_converter: PdfConverter | None = None,
        metrics: Metrics | None = None,
    ):
        self.storage = storage or FileStorageService.default()
        self.pdf = pdf_converter or PdfConverter()
        self.metrics = metrics or get_metrics()
        self._settings = get_settings()

    async def run(
        self,
        session: AsyncSession,
        *,
        template: Template,
        template_version: TemplateVersion,
        context: dict,
        replacements: dict[str, str] | None = None,
        header_text: str | None = None,
        footer_text: str | None = None,
        idempotency_key: str,
        output_basename: str | None = None,
        tenant_id: str | None = None,
    ) -> PipelineRun:
        """Execute rendering and conversion steps within the current asyncio task."""

        (
            tenant_identifier,
            normalized_output_basename,
            replacements_map,
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

        persist_start = perf_counter()
        self.metrics.record_pipeline_stage_start(
            pipeline=PipelineType.DOCUMENT,
            stage=PipelineStage.DATA_PERSISTED,
        )
        try:
            run, created = await self._get_or_create_pending_run(
                session,
                tenant_id=tenant_identifier,
                idempotency_key=idempotency_key,
                template_id=template.id,
                template_version_id=template_version.id,
                payload=context,
                defaults={"result_metadata": {"request": request_metadata}},
            )
        except Exception as exc:
            self.metrics.record_pipeline_stage_end(
                pipeline=PipelineType.DOCUMENT,
                stage=PipelineStage.DATA_PERSISTED,
                result=StageResult.FAILED,
                seconds=perf_counter() - persist_start,
                error_class=exc.__class__.__name__,
            )
            raise
        self.metrics.record_pipeline_stage_end(
            pipeline=PipelineType.DOCUMENT,
            stage=PipelineStage.DATA_PERSISTED,
            result=StageResult.SUCCESS,
            seconds=perf_counter() - persist_start,
        )

        metadata = dict(run.result_metadata or {})
        existing_request = metadata.get("request")

        if run.status in {PipelineRunStatus.RUNNING, PipelineRunStatus.DONE}:
            return run

        if existing_request and existing_request != request_metadata:
            raise ValueError("Idempotency key collision for different pipeline options")
        if not existing_request:
            metadata["request"] = request_metadata
        run.result_metadata = metadata

        if created:
            run.outputs = None
            run.docx_storage_key = None
            run.pdf_storage_key = None
            run.result_s3_key = None
            run.error = None
            run.started_at = None
            run.finished_at = None

        previous_status = run.status
        outputs = self._init_outputs(run)
        run.outputs = outputs

        run.status = PipelineRunStatus.RUNNING
        run.error = None
        run.finished_at = None
        if run.started_at is None:
            run.started_at = datetime.now(tz=timezone.utc)
        await session.flush()

        tenant = get_current_tenant()
        pipeline_start = perf_counter()
        self.metrics.increment_pipeline_inflight(pipeline=PipelineType.DOCUMENT)
        logger.info(
            "Pipeline job started",
            extra={
                "job_id": run.id,
                "template_id": template.id,
                "template_version_id": template_version.id,
                "tenant": tenant.slug,
                "idempotency_key": idempotency_key,
            },
        )

        try:
            self.metrics.observe_pipeline_run(
                template_id=template.id, status=PipelineRunStatus.RUNNING.value
            )
            if (
                previous_status == PipelineRunStatus.ERROR
                and self._stage_completed(outputs, "store")
                and outputs.get("docx_storage_key")
                and outputs.get("pdf_storage_key")
            ):
                docx_key = str(outputs["docx_storage_key"])
                pdf_key = str(outputs["pdf_storage_key"])
                export_status = (outputs.get("stages") or {}).get("export", {}).get("status")
                pdf_fallback = export_status == "fallback"
                pdf_error: str | None = None
                out_base = normalized_output_basename or "resume"
                audit_started = datetime.now(tz=timezone.utc)
                run.status = PipelineRunStatus.DONE
                run.docx_storage_key = docx_key
                run.pdf_storage_key = pdf_key
                outputs["docx"] = docx_key
                outputs["pdf"] = pdf_key
                result_metadata = {
                    "output_basename": out_base,
                    "replacements_applied": len(replacements_map),
                    "header_applied": bool(header_text),
                    "footer_applied": bool(footer_text),
                    "pdf_fallback": pdf_fallback,
                }
                if pdf_error:
                    result_metadata["pdf_error"] = pdf_error
                request_meta = metadata.get("request", request_metadata)
                combined_metadata = {
                    "request": request_meta,
                    "result": result_metadata,
                }
                combined_metadata.update(result_metadata)
                run.result_metadata = combined_metadata
                run.result_s3_key = pdf_key
                run.finished_at = datetime.now(tz=timezone.utc)
                outputs = self._record_stage(
                    outputs,
                    stage="audit",
                    status="success",
                    started_at=audit_started,
                    finished_at=datetime.now(tz=timezone.utc),
                )
                run.outputs = outputs
                await session.commit()
                await session.refresh(run)
                self.metrics.observe_pipeline_run(
                    template_id=template.id, status=PipelineRunStatus.DONE.value
                )
                logger.info(
                    "Pipeline job finished (resume)",
                    extra={
                        "job_id": run.id,
                        "template_id": template.id,
                        "template_version_id": template_version.id,
                        "tenant": tenant.slug,
                        "pdf_fallback": pdf_fallback,
                        "duration_seconds": perf_counter() - pipeline_start,
                    },
                )
                self.metrics.record_pipeline_stage_start(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.COMPLETED,
                )
                self.metrics.record_pipeline_stage_end(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.COMPLETED,
                    result=StageResult.SUCCESS,
                    seconds=0.0,
                )
                self.metrics.observe_pipeline_total_duration(
                    pipeline=PipelineType.DOCUMENT,
                    seconds=perf_counter() - pipeline_start,
                )
                return run
            data_stage_start = datetime.now(tz=timezone.utc)
            if not template_version.payload_key:
                raise RuntimeError("Template version payload missing")
            src = self.storage.get(template_version.payload_key)
            outputs = self._record_stage(
                outputs,
                stage="data_resolve",
                status="success",
                started_at=data_stage_start,
                finished_at=datetime.now(tz=timezone.utc),
            )
            run.outputs = outputs
            await session.flush()

            docx_start = perf_counter()
            self.metrics.record_pipeline_stage_start(
                pipeline=PipelineType.DOCUMENT,
                stage=PipelineStage.DOCX_GENERATED,
            )
            render_started = datetime.now(tz=timezone.utc)
            try:
                rendered = DocxService.render_template(src, context)
            except Exception as exc:
                self.metrics.record_pipeline_stage_end(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.DOCX_GENERATED,
                    result=StageResult.FAILED,
                    seconds=perf_counter() - docx_start,
                    error_class=exc.__class__.__name__,
                )
                outputs = self._record_stage(
                    outputs,
                    stage="template_render",
                    status="error",
                    started_at=render_started,
                    finished_at=datetime.now(tz=timezone.utc),
                )
                run.outputs = outputs
                await session.flush()
                raise
            self.metrics.record_pipeline_stage_end(
                pipeline=PipelineType.DOCUMENT,
                stage=PipelineStage.DOCX_GENERATED,
                result=StageResult.SUCCESS,
                seconds=perf_counter() - docx_start,
            )
            outputs = self._record_stage(
                outputs,
                stage="template_render",
                status="success",
                started_at=render_started,
                finished_at=datetime.now(tz=timezone.utc),
            )
            run.outputs = outputs
            await session.flush()

            replace_started = datetime.now(tz=timezone.utc)
            if replacements_map:
                docx_bytes = DocxService.mass_replace(rendered, replacements_map)
                outputs = self._record_stage(
                    outputs,
                    stage="text_replace",
                    status="success",
                    started_at=replace_started,
                    finished_at=datetime.now(tz=timezone.utc),
                    details={"replacements": len(replacements_map)},
                )
            else:
                docx_bytes = rendered
                outputs = self._record_stage(
                    outputs,
                    stage="text_replace",
                    status="skipped",
                    started_at=replace_started,
                    finished_at=datetime.now(tz=timezone.utc),
                    details={"reason": "no_replacements"},
                )
            run.outputs = outputs
            await session.flush()

            layout_started = datetime.now(tz=timezone.utc)
            if header_text or footer_text:
                docx_bytes = DocxService.set_headers_footers(docx_bytes, header_text, footer_text)
                outputs = self._record_stage(
                    outputs,
                    stage="layout_apply",
                    status="success",
                    started_at=layout_started,
                    finished_at=datetime.now(tz=timezone.utc),
                    details={"header": bool(header_text), "footer": bool(footer_text)},
                )
            else:
                outputs = self._record_stage(
                    outputs,
                    stage="layout_apply",
                    status="skipped",
                    started_at=layout_started,
                    finished_at=datetime.now(tz=timezone.utc),
                    details={"reason": "no_header_footer"},
                )
            run.outputs = outputs
            await session.flush()

            out_base = normalized_output_basename or str(uuid.uuid4())
            now = datetime.now(tz=timezone.utc)
            prefix = build_dated_prefix(tenant.slug, now=now)
            unique_suffix = uuid.uuid4().hex
            docx_key = f"{prefix}/outputs/{out_base}-{unique_suffix}.docx"
            upload_start = perf_counter()
            self.metrics.record_pipeline_stage_start(
                pipeline=PipelineType.DOCUMENT,
                stage=PipelineStage.STORED_S3,
            )
            try:
                self.storage.put(docx_key, docx_bytes, content_type=self.DOCX_CONTENT_TYPE)
            except Exception as exc:
                self.metrics.record_pipeline_stage_end(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.STORED_S3,
                    result=StageResult.FAILED,
                    seconds=perf_counter() - upload_start,
                    error_class=exc.__class__.__name__,
                )
                raise
            self.metrics.record_pipeline_stage_end(
                pipeline=PipelineType.DOCUMENT,
                stage=PipelineStage.STORED_S3,
                result=StageResult.SUCCESS,
                seconds=perf_counter() - upload_start,
            )

            pdf_fallback = False
            pdf_error = None  # str | None
            pdf_duration = 0.0
            export_started = datetime.now(tz=timezone.utc)
            with tempfile.TemporaryDirectory() as td:
                temp_dir = Path(td)
                p_in = temp_dir / "in.docx"
                p_out_dir = temp_dir / "out"
                p_in.write_bytes(docx_bytes)
                pdf_start = perf_counter()
                self.metrics.record_pipeline_stage_start(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.PDF_CONVERTED,
                )
                try:
                    conversion: PdfConversionResult = self.pdf.convert(p_in, p_out_dir)
                except PdfConversionError as exc:
                    pdf_duration = perf_counter() - pdf_start
                    pdf_error_raw = str(exc) or "pdf_conversion_failed"
                    pdf_error = sanitize_label(pdf_error_raw)
                    self.metrics.record_pipeline_stage_end(
                        pipeline=PipelineType.DOCUMENT,
                        stage=PipelineStage.PDF_CONVERTED,
                        result=StageResult.FAILED,
                        seconds=pdf_duration,
                        error_class=pdf_error,
                    )
                    pdf_bytes = MINI_PDF_BYTES
                    pdf_fallback = True
                    logger.warning(
                        "PDF conversion failed; using fallback PDF",
                        extra={
                            "job_id": run.id,
                            "template_id": template.id,
                            "template_version_id": template_version.id,
                            "tenant": tenant.slug,
                            "error_code": pdf_error,
                        },
                    )
                except RuntimeError as exc:
                    logger.exception("LibreOffice PDF conversion failed")
                    pdf_bytes = MINI_PDF_BYTES
                    pdf_fallback = True
                    pdf_duration = perf_counter() - pdf_start
                    pdf_error_raw = str(exc) or "pdf_conversion_failed"
                    pdf_error = sanitize_label(pdf_error_raw)
                    self.metrics.record_pipeline_stage_end(
                        pipeline=PipelineType.DOCUMENT,
                        stage=PipelineStage.PDF_CONVERTED,
                        result=StageResult.FAILED,
                        seconds=pdf_duration,
                        error_class=pdf_error,
                    )
                    logger.warning(
                        "PDF conversion failed; using fallback PDF",
                        extra={
                            "job_id": run.id,
                            "template_id": template.id,
                            "template_version_id": template_version.id,
                            "tenant": tenant.slug,
                            "error_code": pdf_error,
                        },
                    )
                else:
                    pdf_duration = perf_counter() - pdf_start
                    pdf_bytes = conversion.path.read_bytes()
                    pdf_fallback = conversion.fallback_used
                    if conversion.error_code:
                        pdf_error = sanitize_label(conversion.error_code)
                        self.metrics.record_pipeline_error(
                            pipeline=PipelineType.DOCUMENT,
                            stage=PipelineStage.PDF_CONVERTED,
                            error_class=pdf_error,
                        )
                    self.metrics.record_pipeline_stage_end(
                        pipeline=PipelineType.DOCUMENT,
                        stage=PipelineStage.PDF_CONVERTED,
                        result=StageResult.FALLBACK if pdf_fallback else StageResult.SUCCESS,
                        seconds=pdf_duration,
                    )
                finally:
                    self.metrics.observe_pdf_duration(
                        template_id=template.id,
                        seconds=pdf_duration,
                    )
            outputs = self._record_stage(
                outputs,
                stage="export",
                status="success" if not pdf_fallback else "fallback",
                started_at=export_started,
                finished_at=datetime.now(tz=timezone.utc),
                details={"pdf_fallback": pdf_fallback},
            )
            qr_started = datetime.now(tz=timezone.utc)
            if self._settings.doc_pipeline_enable_qr:
                self.metrics.record_pipeline_stage_start(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.QR_CODE_APPLIED,
                )
                try:
                    pdf_bytes = self._apply_qr_code_to_pdf(pdf_bytes, self._qr_payload(run))
                except StampingUnavailableError:
                    # Feature enabled but no real stamping backend ships: leave the PDF
                    # untouched and record an honest "requested but not applied" instead
                    # of a misleading success or a spurious error.
                    self.metrics.record_pipeline_stage_end(
                        pipeline=PipelineType.DOCUMENT,
                        stage=PipelineStage.QR_CODE_APPLIED,
                        result=StageResult.SKIPPED,
                        seconds=0.0,
                    )
                    outputs = self._record_stage(
                        outputs,
                        stage="qr_code",
                        status="skipped",
                        started_at=qr_started,
                        finished_at=datetime.now(tz=timezone.utc),
                        details={"reason": "stamping_backend_unavailable"},
                    )
                except Exception as exc:  # pragma: no cover - defensive fallback
                    self.metrics.record_pipeline_stage_end(
                        pipeline=PipelineType.DOCUMENT,
                        stage=PipelineStage.QR_CODE_APPLIED,
                        result=StageResult.FAILED,
                        seconds=0.0,
                        error_class=exc.__class__.__name__,
                    )
                    outputs = self._record_stage(
                        outputs,
                        stage="qr_code",
                        status="error",
                        started_at=qr_started,
                        finished_at=datetime.now(tz=timezone.utc),
                        details={"error": exc.__class__.__name__},
                    )
                else:
                    self.metrics.record_pipeline_stage_end(
                        pipeline=PipelineType.DOCUMENT,
                        stage=PipelineStage.QR_CODE_APPLIED,
                        result=StageResult.SUCCESS,
                        seconds=0.0,
                    )
                    outputs = self._record_stage(
                        outputs,
                        stage="qr_code",
                        status="success",
                        started_at=qr_started,
                        finished_at=datetime.now(tz=timezone.utc),
                        details={"payload": self._qr_payload(run)},
                    )
            else:
                self.metrics.record_pipeline_stage_start(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.QR_CODE_APPLIED,
                )
                self.metrics.record_pipeline_stage_end(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.QR_CODE_APPLIED,
                    result=StageResult.SKIPPED,
                    seconds=0.0,
                )
                outputs = self._record_stage(
                    outputs,
                    stage="qr_code",
                    status="skipped",
                    started_at=qr_started,
                    finished_at=datetime.now(tz=timezone.utc),
                    details={"reason": "disabled"},
                )

            watermark_started = datetime.now(tz=timezone.utc)
            if self._settings.doc_pipeline_enable_watermark:
                self.metrics.record_pipeline_stage_start(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.WATERMARK_APPLIED,
                )
                try:
                    pdf_bytes = self._apply_watermark_to_pdf(
                        pdf_bytes, self._settings.doc_pipeline_watermark_text
                    )
                except StampingUnavailableError:
                    # See the QR branch: honest "requested but not applied".
                    self.metrics.record_pipeline_stage_end(
                        pipeline=PipelineType.DOCUMENT,
                        stage=PipelineStage.WATERMARK_APPLIED,
                        result=StageResult.SKIPPED,
                        seconds=0.0,
                    )
                    outputs = self._record_stage(
                        outputs,
                        stage="watermark",
                        status="skipped",
                        started_at=watermark_started,
                        finished_at=datetime.now(tz=timezone.utc),
                        details={"reason": "stamping_backend_unavailable"},
                    )
                except Exception as exc:  # pragma: no cover - defensive fallback
                    self.metrics.record_pipeline_stage_end(
                        pipeline=PipelineType.DOCUMENT,
                        stage=PipelineStage.WATERMARK_APPLIED,
                        result=StageResult.FAILED,
                        seconds=0.0,
                        error_class=exc.__class__.__name__,
                    )
                    outputs = self._record_stage(
                        outputs,
                        stage="watermark",
                        status="error",
                        started_at=watermark_started,
                        finished_at=datetime.now(tz=timezone.utc),
                        details={"error": exc.__class__.__name__},
                    )
                else:
                    self.metrics.record_pipeline_stage_end(
                        pipeline=PipelineType.DOCUMENT,
                        stage=PipelineStage.WATERMARK_APPLIED,
                        result=StageResult.SUCCESS,
                        seconds=0.0,
                    )
                    outputs = self._record_stage(
                        outputs,
                        stage="watermark",
                        status="success",
                        started_at=watermark_started,
                        finished_at=datetime.now(tz=timezone.utc),
                        details={"text": self._settings.doc_pipeline_watermark_text},
                    )
            else:
                self.metrics.record_pipeline_stage_start(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.WATERMARK_APPLIED,
                )
                self.metrics.record_pipeline_stage_end(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.WATERMARK_APPLIED,
                    result=StageResult.SKIPPED,
                    seconds=0.0,
                )
                outputs = self._record_stage(
                    outputs,
                    stage="watermark",
                    status="skipped",
                    started_at=watermark_started,
                    finished_at=datetime.now(tz=timezone.utc),
                    details={"reason": "disabled"},
                )
            stages = outputs.get("stages") or {}
            if not self._settings.doc_pipeline_enable_qr and "qr_code" not in stages:
                outputs = self._record_stage(
                    outputs,
                    stage="qr_code",
                    status="skipped",
                    started_at=qr_started,
                    finished_at=datetime.now(tz=timezone.utc),
                    details={"reason": "disabled"},
                )
                stages = outputs.get("stages") or {}
            if not self._settings.doc_pipeline_enable_watermark and "watermark" not in stages:
                outputs = self._record_stage(
                    outputs,
                    stage="watermark",
                    status="skipped",
                    started_at=watermark_started,
                    finished_at=datetime.now(tz=timezone.utc),
                    details={"reason": "disabled"},
                )
            run.outputs = outputs
            await session.flush()
            pdf_key = f"{prefix}/outputs/{out_base}-{unique_suffix}.pdf"
            upload_start = perf_counter()
            store_started = datetime.now(tz=timezone.utc)
            self.metrics.record_pipeline_stage_start(
                pipeline=PipelineType.DOCUMENT,
                stage=PipelineStage.STORED_S3,
            )
            try:
                self.storage.put(pdf_key, pdf_bytes, content_type="application/pdf")
            except Exception as exc:
                self.metrics.record_pipeline_stage_end(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.STORED_S3,
                    result=StageResult.FAILED,
                    seconds=perf_counter() - upload_start,
                    error_class=exc.__class__.__name__,
                )
                outputs = self._record_stage(
                    outputs,
                    stage="store",
                    status="error",
                    started_at=store_started,
                    finished_at=datetime.now(tz=timezone.utc),
                )
                run.outputs = outputs
                await session.flush()
                raise
            self.metrics.record_pipeline_stage_end(
                pipeline=PipelineType.DOCUMENT,
                stage=PipelineStage.STORED_S3,
                result=StageResult.SUCCESS,
                seconds=perf_counter() - upload_start,
            )
            self.metrics.record_pipeline_stage_start(
                pipeline=PipelineType.DOCUMENT,
                stage=PipelineStage.STAMPED_QR_APPLIED,
            )
            self.metrics.record_pipeline_stage_end(
                pipeline=PipelineType.DOCUMENT,
                stage=PipelineStage.STAMPED_QR_APPLIED,
                result=StageResult.SKIPPED,
                seconds=0.0,
            )
            outputs["docx_storage_key"] = docx_key
            outputs["pdf_storage_key"] = pdf_key
            outputs = self._record_stage(
                outputs,
                stage="store",
                status="success",
                started_at=store_started,
                finished_at=datetime.now(tz=timezone.utc),
                details={"docx": docx_key, "pdf": pdf_key},
            )
            run.outputs = outputs
            await session.flush()

            audit_started = datetime.now(tz=timezone.utc)
            run.status = PipelineRunStatus.DONE
            run.docx_storage_key = docx_key
            run.pdf_storage_key = pdf_key
            outputs["docx"] = docx_key
            outputs["pdf"] = pdf_key
            result_metadata = {
                "output_basename": out_base,
                "replacements_applied": len(replacements_map),
                "header_applied": bool(header_text),
                "footer_applied": bool(footer_text),
                "pdf_fallback": pdf_fallback,
            }
            if pdf_error:
                result_metadata["pdf_error"] = pdf_error
            request_meta = metadata.get("request", request_metadata)
            combined_metadata = {
                "request": request_meta,
                "result": result_metadata,
            }
            combined_metadata.update(result_metadata)
            run.result_metadata = combined_metadata
            run.result_s3_key = pdf_key
            run.finished_at = datetime.now(tz=timezone.utc)
            outputs = self._record_stage(
                outputs,
                stage="audit",
                status="success",
                started_at=audit_started,
                finished_at=datetime.now(tz=timezone.utc),
            )
            run.outputs = outputs
            await session.commit()
            await session.refresh(run)
            self.metrics.observe_pipeline_run(
                template_id=template.id, status=PipelineRunStatus.DONE.value
            )
            logger.info(
                "Pipeline job finished",
                extra={
                    "job_id": run.id,
                    "template_id": template.id,
                    "template_version_id": template_version.id,
                    "tenant": tenant.slug,
                    "pdf_fallback": pdf_fallback,
                    "duration_seconds": perf_counter() - pipeline_start,
                },
            )
            self.metrics.record_pipeline_stage_start(
                pipeline=PipelineType.DOCUMENT,
                stage=PipelineStage.COMPLETED,
            )
            self.metrics.record_pipeline_stage_end(
                pipeline=PipelineType.DOCUMENT,
                stage=PipelineStage.COMPLETED,
                result=StageResult.SUCCESS,
                seconds=0.0,
            )
            self.metrics.observe_pipeline_total_duration(
                pipeline=PipelineType.DOCUMENT,
                seconds=perf_counter() - pipeline_start,
            )
            return run
        except Exception as exc:
            logger.exception(
                "Pipeline job failed",
                extra={
                    "job_id": run.id,
                    "template_id": template.id,
                    "template_version_id": template_version.id,
                    "tenant": tenant.slug,
                },
            )
            run.status = PipelineRunStatus.ERROR
            run.docx_storage_key = None
            run.pdf_storage_key = None
            run.outputs = outputs
            error_label, metrics_code = self._normalize_error_details(exc)
            run.error = error_label
            request_meta = metadata.get("request", request_metadata)
            run.result_metadata = {
                "request": request_meta,
                "error": error_label,
            }
            run.finished_at = datetime.now(tz=timezone.utc)
            await session.commit()
            await session.refresh(run)
            self.metrics.observe_pipeline_run(
                template_id=template.id, status=PipelineRunStatus.ERROR.value
            )
            self.metrics.record_pipeline_stage_start(
                pipeline=PipelineType.DOCUMENT,
                stage=PipelineStage.FAILED,
            )
            self.metrics.record_pipeline_stage_end(
                pipeline=PipelineType.DOCUMENT,
                stage=PipelineStage.FAILED,
                result=StageResult.FAILED,
                seconds=0.0,
                error_class=metrics_code,
            )
            self.metrics.observe_pipeline_total_duration(
                pipeline=PipelineType.DOCUMENT,
                seconds=perf_counter() - pipeline_start,
            )
            raise
        finally:
            self.metrics.decrement_pipeline_inflight(pipeline=PipelineType.DOCUMENT)
