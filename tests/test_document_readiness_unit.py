"""Unit tests for document readiness (TZ §9.5)."""

from __future__ import annotations

from types import SimpleNamespace

from app.models.document import DocumentStatus
from app.models.models import TemplateVersionStatus
from app.modules.pipelines.document_core_profile import DOCUMENT_CORE_PIPELINE_STEPS
from app.services.document_readiness import compute_document_readiness


def test_readiness_revoked_is_zero() -> None:
    doc = SimpleNamespace(
        status=DocumentStatus.REVOKED,
        template_version_id="tv",
        template_version=SimpleNamespace(status=TemplateVersionStatus.ACTIVE),
        company_id="c",
        versions=[],
        storage_key=None,
        file_id=None,
    )
    snap = compute_document_readiness(doc)  # type: ignore[arg-type]
    assert snap.score == 0
    assert snap.blockers
    assert snap.recommended_actions
    assert len(snap.pipeline_stages) == len(DOCUMENT_CORE_PIPELINE_STEPS)


def test_readiness_happy_path_bumps_score() -> None:
    version = SimpleNamespace(
        version_number=1,
        created_at=None,
        file_key="s3://x/doc.docx",
        file_id="f1",
        data_json={"role": "worker"},
        approval_status="approved",
        signature_status="signed",
        edo_status="delivered",
    )
    doc = SimpleNamespace(
        status=DocumentStatus.SIGNED,
        template_version_id="tv",
        template_version=SimpleNamespace(status=TemplateVersionStatus.ACTIVE),
        company_id="c",
        versions=[version],
        storage_key=None,
        file_id=None,
    )
    snap = compute_document_readiness(doc)  # type: ignore[arg-type]
    assert snap.score >= 70
    assert not snap.blockers
    assert len(snap.pipeline_stages) == len(DOCUMENT_CORE_PIPELINE_STEPS)
    assert all(s.stage_id for s in snap.pipeline_stages)


def test_readiness_render_stage_detail_when_no_file() -> None:
    """Срез-139: подделка «job=PROCESSING» убрана — у документа такого состояния
    не бывает (генерация создаёт строку только по завершении). Единственная
    честная причина незавершённой выкладки — нет файла результата."""
    doc = SimpleNamespace(
        status=DocumentStatus.DRAFT,
        template_version_id="tv",
        template_version=SimpleNamespace(status=TemplateVersionStatus.ACTIVE),
        company_id="c",
        versions=[],
        storage_key=None,
        file_id=None,
    )
    snap = compute_document_readiness(doc)  # type: ignore[arg-type]
    render = next(s for s in snap.pipeline_stages if s.stage_id == "render_docx")
    assert render.complete is False
    assert render.detail == "Нет файла результата"
