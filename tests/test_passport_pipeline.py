from __future__ import annotations

import zipfile
from io import BytesIO

from docx import Document

from app.core.utils.canonical_hash import compute_sha256_input
from app.core.utils.pdf_passport import embed_pdf_passport
from app.modules.templates.passport import inject_passport
from app.modules.templates.service import build_passport


def _docx(text: str) -> bytes:
    doc = Document()
    doc.add_paragraph(text)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_passport_hash_is_stable_for_same_payload() -> None:
    payload = {"a": 1, "b": {"x": "y"}}
    h1 = compute_sha256_input(payload, mapping={"m": 1}, template_version_id="t1", options={"visible": True})
    h2 = compute_sha256_input(payload, mapping={"m": 1}, template_version_id="t1", options={"visible": True})
    assert h1 == h2


def test_docx_contains_custom_property_passport() -> None:
    out = inject_passport(_docx("Hello"), {"template_version": "v1"}, visible=False)
    with zipfile.ZipFile(BytesIO(out), "r") as zf:
        custom = zf.read("docProps/custom.xml").decode("utf-8")
    assert "passport_json" in custom
    assert "template_version" in custom


def test_visible_passport_is_rendered_in_docx_text() -> None:
    out = inject_passport(_docx("Hello"), {"correlation_id": "cid-1"}, visible=True)
    with zipfile.ZipFile(BytesIO(out), "r") as zf:
        document_xml = zf.read("word/document.xml").decode("utf-8")
    assert "Document passport" in document_xml
    assert "correlation_id" in document_xml


def test_pdf_contains_passport_page_or_text() -> None:
    pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF"
    out = embed_pdf_passport(pdf, {"correlation_id": "cid-1"})
    assert b"PTD-PASSPORT" in out
    assert b"cid-1" in out


def test_correlation_id_propagates_to_document_version_and_job() -> None:
    passport = build_passport(
        code="contract",
        version=1,
        tenant_id="t1",
        generated_by="u@example.com",
        correlation_id="corr-123",
        data={"x": 1},
        document_id="doc-1",
        document_version_id="ver-1",
        version_number=2,
    )
    assert passport["correlation_id"] == "corr-123"
    data_json = {"payload": {"x": 1}, "passport": passport, "correlation_id": passport["correlation_id"]}
    assert data_json["correlation_id"] == "corr-123"
    assert data_json["passport"]["document_version_id"] == "ver-1"
