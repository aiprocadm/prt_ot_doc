"""Unit tests for document readiness (TZ §9.5)."""

from __future__ import annotations

from types import SimpleNamespace

from app.models.document import DocumentJobStatus, DocumentStatus
from app.models.models import TemplateVersionStatus
from app.services.document_readiness import compute_document_readiness


def test_readiness_revoked_is_zero() -> None:
    doc = SimpleNamespace(
        status=DocumentStatus.REVOKED,
        template_version_id="tv",
        template_version=SimpleNamespace(status=TemplateVersionStatus.ACTIVE),
        company_id="c",
        job=None,
        versions=[],
        storage_key=None,
        file_id=None,
    )
    snap = compute_document_readiness(doc)  # type: ignore[arg-type]
    assert snap.score == 0
    assert snap.blockers
    assert snap.recommended_actions


def test_readiness_happy_path_bumps_score() -> None:
    version = SimpleNamespace(
        version_number=1,
        created_at=None,
        file_key="s3://x/doc.docx",
        file_id="f1",
        approval_status="approved",
        signature_status="signed",
        edo_status="delivered",
    )
    doc = SimpleNamespace(
        status=DocumentStatus.SIGNED,
        template_version_id="tv",
        template_version=SimpleNamespace(status=TemplateVersionStatus.ACTIVE),
        company_id="c",
        job=SimpleNamespace(status=DocumentJobStatus.SUCCEEDED),
        versions=[version],
        storage_key=None,
        file_id=None,
    )
    snap = compute_document_readiness(doc)  # type: ignore[arg-type]
    assert snap.score >= 70
    assert not snap.blockers
