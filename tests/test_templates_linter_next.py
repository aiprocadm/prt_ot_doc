from io import BytesIO
from zipfile import ZipFile

from app.modules.templates.linter import lint_template


def _docx_with_text(text: str) -> bytes:
    bio = BytesIO()
    xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>
</w:document>""".encode()
    with ZipFile(bio, "w") as zf:
        zf.writestr("word/document.xml", xml)
    return bio.getvalue()


def test_linter_balanced_blocks() -> None:
    report = lint_template(_docx_with_text("{% if employee.name %}{{ employee.name }}{% endif %}"))
    assert report["summary"]["error_count"] == 0
    assert "employee.name" in report["found_fields"]


def test_linter_unbalanced_blocks() -> None:
    report = lint_template(_docx_with_text("{% if employee.name %}{{ employee.name }}"))
    assert report["summary"]["error_count"] > 0
