"""PipelineService QR/watermark stamping backends (ARCH-4 slice 9 split)."""

from __future__ import annotations

from app.models.models import PipelineRun
from app.services.pipeline._base import StampingUnavailableError


class StampingMixin:
    """Default (placeholder) QR-code and watermark stage backends."""

    def _qr_payload(self, run: PipelineRun) -> str:
        metadata = dict(run.result_metadata or {})
        request_meta = metadata.get("request") or {}
        document_version_id = request_meta.get("document_version_id")
        return str(document_version_id or run.id)

    def _apply_qr_code_to_pdf(self, pdf_bytes: bytes, payload: str) -> bytes:
        """Default QR-code stage backend.

        No real QR stamping ships yet. Rather than silently returning the PDF
        unchanged (which the pipeline would record as a successful stage and
        mislead callers into trusting an unstamped document), signal that the
        backend is unavailable so the stage is recorded honestly as ``skipped``.
        Override this method (or inject a real backend) to enable stamping.
        """
        _ = (pdf_bytes, payload)
        raise StampingUnavailableError("qr_code")

    def _apply_watermark_to_pdf(self, pdf_bytes: bytes, text: str) -> bytes:
        """Default watermark stage backend.

        See :meth:`_apply_qr_code_to_pdf` — no real watermarking ships yet, so this
        raises instead of falsely reporting an applied watermark.
        """
        _ = (pdf_bytes, text)
        raise StampingUnavailableError("watermark")
