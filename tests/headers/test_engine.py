from io import BytesIO
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

from app.modules.headers.engine import apply_headers_to_docx


def _docx_stub() -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            """<?xml version='1.0' encoding='UTF-8' standalone='yes'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'><Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/><Default Extension='xml' ContentType='application/xml'/><Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/><Override PartName='/word/settings.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml'/></Types>""",
        )
        z.writestr(
            "word/document.xml",
            """<?xml version='1.0' encoding='UTF-8' standalone='yes'?><w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p/><w:sectPr/></w:body></w:document>""",
        )
        z.writestr(
            "word/settings.xml",
            """<?xml version='1.0' encoding='UTF-8' standalone='yes'?><w:settings xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'/>""",
        )
    return buf.getvalue()


def test_apply_headers_adds_parts_relationships_and_page_fields() -> None:
    preset = SimpleNamespace(
        different_first=True,
        different_odd_even=True,
        header_first_xml="first {{organization.short_name}}",
        header_odd_xml="left\ncenter {PAGE}\nright {NUMPAGES}",
        header_even_xml="even {{branch.name}}",
        footer_first_xml="footer-first",
        footer_odd_xml="footer {{doc.title}}",
        footer_even_xml="footer-even",
        watermark={"enabled": True, "text": "DRAFT"},
    )
    out, report = apply_headers_to_docx(
        docx_bytes=_docx_stub(),
        preset=preset,
        context={"doc": {"title": "T1"}, "organization": {"short_name": "ACME"}, "branch": {"name": "North"}},
    )
    with ZipFile(BytesIO(out), "r") as z:
        assert "word/header1.xml" in z.namelist()
        assert "word/header2.xml" in z.namelist()
        assert "word/header3.xml" in z.namelist()
        assert "word/footer1.xml" in z.namelist()
        assert "word/footer2.xml" in z.namelist()
        assert "word/footer3.xml" in z.namelist()
        header = z.read("word/header2.xml").decode("utf-8")
        rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
        document = z.read("word/document.xml").decode("utf-8")
        assert "fldSimple" in header
        assert "PAGE" in header
        assert "NUMPAGES" in header
        assert "WATERMARK:DRAFT" in header
        assert "Relationship" in rels
        assert "headerReference" in document
        assert "footerReference" in document
    assert "PAGE" in report.fields_added
    assert "NUMPAGES" in report.fields_added
