from __future__ import annotations

from io import BytesIO
import re
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

from app.modules.headers.placeholders import render_placeholders
from app.modules.headers.report import ApplyHeadersReport

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

NS = {"w": W_NS, "r": R_NS}


def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def _container_xml(content: str) -> bytes:
    root = etree.Element(_w("hdr"))
    tbl = etree.SubElement(root, _w("tbl"))
    tbl_pr = etree.SubElement(tbl, _w("tblPr"))
    tbl_w = etree.SubElement(tbl_pr, _w("tblW"))
    tbl_w.set(_w("type"), "pct")
    tbl_w.set(_w("w"), "5000")
    grid = etree.SubElement(tbl, _w("tblGrid"))
    grid_col = etree.SubElement(grid, _w("gridCol"))
    grid_col.set(_w("w"), "9000")
    tr = etree.SubElement(tbl, _w("tr"))
    tc = etree.SubElement(tr, _w("tc"))
    tc_pr = etree.SubElement(tc, _w("tcPr"))
    etree.SubElement(tc_pr, _w("tcW"), attrib={_w("w"): "9000", _w("type"): "dxa"})

    for align, line in zip(["left", "center", "right"], content.split("\n")[:3] + [""] * 3):
        p = etree.SubElement(tc, _w("p"))
        p_pr = etree.SubElement(p, _w("pPr"))
        etree.SubElement(p_pr, _w("jc"), attrib={_w("val"): align})
        r = etree.SubElement(p, _w("r"))
        if "{PAGE}" in line:
            fld = etree.SubElement(p, _w("fldSimple"), attrib={_w("instr"): " PAGE "})
            rr = etree.SubElement(fld, _w("r"))
            etree.SubElement(rr, _w("t")).text = "1"
            line = line.replace("{PAGE}", "")
        if "{NUMPAGES}" in line:
            fld = etree.SubElement(p, _w("fldSimple"), attrib={_w("instr"): " NUMPAGES "})
            rr = etree.SubElement(fld, _w("r"))
            etree.SubElement(rr, _w("t")).text = "1"
            line = line.replace("{NUMPAGES}", "")
        etree.SubElement(r, _w("t")).text = line

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")


def apply_headers_to_docx(
    *,
    docx_bytes: bytes,
    preset: object,
    context: dict,
    watermark_override: dict | None = None,
) -> tuple[bytes, ApplyHeadersReport]:
    report = ApplyHeadersReport()
    in_buf = BytesIO(docx_bytes)
    out_buf = BytesIO()

    with ZipFile(in_buf, "r") as zin, ZipFile(out_buf, "w", ZIP_DEFLATED) as zout:
        files = {name: zin.read(name) for name in zin.namelist()}
        document = etree.fromstring(files["word/document.xml"])
        sect = document.xpath("//w:sectPr", namespaces=NS)
        if sect:
            sect_pr = sect[-1]
            if getattr(preset, "different_first", False):
                etree.SubElement(sect_pr, _w("titlePg"))
            if getattr(preset, "different_odd_even", False):
                settings_xml = files.get("word/settings.xml")
                if settings_xml:
                    settings_root = etree.fromstring(settings_xml)
                    etree.SubElement(settings_root, _w("evenAndOddHeaders"))
                    files["word/settings.xml"] = etree.tostring(settings_root, xml_declaration=True, encoding="UTF-8", standalone="yes")

        unresolved: list[str] = []
        header_src = getattr(preset, "header_odd_xml", "") or ""
        footer_src = getattr(preset, "footer_odd_xml", "") or ""
        wm = watermark_override if watermark_override is not None else (getattr(preset, "watermark", {}) or {})
        if wm.get("enabled") and wm.get("text"):
            header_src = (header_src + "\n" + f"WATERMARK:{wm['text']}").strip()
        header_rendered, unresolved_h = render_placeholders(header_src, context, strict=True)
        footer_rendered, unresolved_f = render_placeholders(footer_src, context, strict=True)
        unresolved.extend(unresolved_h + unresolved_f)

        files["word/header1.xml"] = _container_xml(header_rendered)
        files["word/footer1.xml"] = _container_xml(footer_rendered).replace(b"<w:hdr", b"<w:ftr").replace(b"</w:hdr>", b"</w:ftr>")
        report.changed_parts.extend(["word/document.xml", "word/header1.xml", "word/footer1.xml"])
        report.unresolved_placeholders = sorted(set(unresolved))

        if re.search(r"\{PAGE\}", header_src + footer_src):
            report.fields_added.append("PAGE")
        if re.search(r"\{NUMPAGES\}", header_src + footer_src):
            report.fields_added.append("NUMPAGES")

        files["word/document.xml"] = etree.tostring(document, xml_declaration=True, encoding="UTF-8", standalone="yes")

        for name, payload in files.items():
            zout.writestr(name, payload)

    return out_buf.getvalue(), report
