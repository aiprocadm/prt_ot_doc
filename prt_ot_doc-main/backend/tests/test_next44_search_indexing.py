from __future__ import annotations

from pathlib import Path

from app.modules.files import extractors


def test_extract_text_docx_paragraphs_and_tables(tmp_path: Path) -> None:
    docx = __import__("docx")
    doc = docx.Document()
    doc.add_paragraph("Привет мир")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Колонка"
    table.cell(0, 1).text = "Значение"
    path = tmp_path / "sample.docx"
    doc.save(path)

    text = extractors.extract_text_docx(path)

    assert "Привет мир" in text
    assert "Колонка" in text
    assert "Значение" in text


def test_extract_text_pdf_cyrillic_with_reader_fallback(monkeypatch) -> None:
    class _Page:
        def extract_text(self):
            return "Тестовый PDF"

    class _Reader:
        def __init__(self, *_args, **_kwargs):
            self.pages = [_Page()]

    class _PypdfModule:
        PdfReader = _Reader

    monkeypatch.setitem(__import__("sys").modules, "pypdf", _PypdfModule())

    text = extractors.extract_text_pdf(Path("/tmp/fake.pdf"))
    assert "Тестовый PDF" in text


def test_normalize_text() -> None:
    assert extractors.normalize_text("a\x00\n\n b") == "a b"
