from __future__ import annotations

import re
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

from app.core.xml_security import lxml_fromstring
from app.modules.headers.placeholders import render_placeholders
from app.modules.headers.report import ApplyHeadersReport

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
WORD_HEADER_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/header"
WORD_FOOTER_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer"

NS = {"w": W_NS, "r": R_NS, "rel": REL_NS, "ct": CONTENT_TYPES_NS}


def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def _rel(tag: str) -> str:
    return f"{{{REL_NS}}}{tag}"


def _ct(tag: str) -> str:
    return f"{{{CONTENT_TYPES_NS}}}{tag}"


def _container_xml(content: str, *, kind: str) -> bytes:
    root = etree.Element(_w("hdr" if kind == "header" else "ftr"))
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

    lines = content.split("\n") if content else [""]
    for idx, line in enumerate(lines):
        align = ["left", "center", "right"][idx] if idx < 3 else "left"
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


def _ensure_settings_flag(files: dict[str, bytes], tag: str) -> None:
    settings_xml = files.get("word/settings.xml")
    if not settings_xml:
        return
    settings_root = lxml_fromstring(settings_xml)  # разд. 64.2: защита от XXE
    if settings_root.find(f"w:{tag}", namespaces=NS) is None:
        etree.SubElement(settings_root, _w(tag))
    files["word/settings.xml"] = etree.tostring(
        settings_root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone="yes",
    )


def _ensure_document_relationships(files: dict[str, bytes]) -> etree._Element:
    rels_path = "word/_rels/document.xml.rels"
    if rels_path in files:
        return lxml_fromstring(files[rels_path])  # разд. 64.2: защита от XXE
    root = etree.Element(_rel("Relationships"), nsmap={None: REL_NS})
    files[rels_path] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone="yes"
    )
    return root


def _next_rid(root: etree._Element) -> str:
    ids = []
    for rel in root.findall("rel:Relationship", namespaces=NS):
        rel_id = rel.get("Id", "")
        if rel_id.startswith("rId") and rel_id[3:].isdigit():
            ids.append(int(rel_id[3:]))
    return f"rId{(max(ids) if ids else 0) + 1}"


def _ensure_content_type_override(
    files: dict[str, bytes], *, part_name: str, content_type: str
) -> None:
    if "[Content_Types].xml" not in files:
        root = etree.Element(_ct("Types"), nsmap={None: CONTENT_TYPES_NS})
        etree.SubElement(
            root,
            _ct("Default"),
            Extension="rels",
            ContentType="application/vnd.openxmlformats-package.relationships+xml",
        )
        etree.SubElement(root, _ct("Default"), Extension="xml", ContentType="application/xml")
    else:
        root = lxml_fromstring(files["[Content_Types].xml"])  # разд. 64.2: защита от XXE
    existing = root.xpath(f"/ct:Types/ct:Override[@PartName='/{part_name}']", namespaces=NS)
    if not existing:
        etree.SubElement(root, _ct("Override"), PartName=f"/{part_name}", ContentType=content_type)
    files["[Content_Types].xml"] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone="yes"
    )


def _bind_section_part(
    sect_pr: etree._Element,
    rels_root: etree._Element,
    files: dict[str, bytes],
    *,
    part_name: str,
    content: str,
    kind: str,
    ref_type: str,
) -> None:
    rid = _next_rid(rels_root)
    etree.SubElement(
        rels_root,
        _rel("Relationship"),
        Id=rid,
        Type=WORD_HEADER_REL if kind == "header" else WORD_FOOTER_REL,
        Target=part_name,
    )
    files[f"word/{part_name}"] = _container_xml(content, kind=kind)
    _ensure_content_type_override(
        files,
        part_name=f"word/{part_name}",
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"
            if kind == "header"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"
        ),
    )
    tag = "headerReference" if kind == "header" else "footerReference"
    for existing in list(sect_pr.findall(f"w:{tag}", namespaces=NS)):
        if existing.get(_w("type")) == ref_type:
            sect_pr.remove(existing)
    etree.SubElement(sect_pr, _w(tag), attrib={_w("type"): ref_type, f"{{{R_NS}}}id": rid})


def _resolve_section_content(preset: object, prefix: str, fallback_key: str) -> str:
    value = getattr(preset, f"{prefix}_{fallback_key}_xml", None)
    if value:
        return value
    return getattr(preset, f"{prefix}_odd_xml", "") or ""


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
        document = lxml_fromstring(files["word/document.xml"])  # разд. 64.2: защита от XXE
        sect = document.xpath("//w:sectPr", namespaces=NS)
        if not sect:
            raise ValueError("DOCX does not contain sectPr")
        sect_pr = sect[-1]
        rels_root = _ensure_document_relationships(files)

        if getattr(preset, "different_first", False):
            if sect_pr.find("w:titlePg", namespaces=NS) is None:
                etree.SubElement(sect_pr, _w("titlePg"))
        if getattr(preset, "different_odd_even", False):
            _ensure_settings_flag(files, "evenAndOddHeaders")

        unresolved: list[str] = []
        watermark = (
            watermark_override
            if watermark_override is not None
            else (getattr(preset, "watermark", {}) or {})
        )
        part_specs = [
            ("header", "first", "header1.xml", _resolve_section_content(preset, "header", "first")),
            ("header", "default", "header2.xml", _resolve_section_content(preset, "header", "odd")),
            ("header", "even", "header3.xml", _resolve_section_content(preset, "header", "even")),
            ("footer", "first", "footer1.xml", _resolve_section_content(preset, "footer", "first")),
            ("footer", "default", "footer2.xml", _resolve_section_content(preset, "footer", "odd")),
            ("footer", "even", "footer3.xml", _resolve_section_content(preset, "footer", "even")),
        ]
        for kind, ref_type, part_name, source in part_specs:
            if (
                watermark.get("enabled")
                and watermark.get("text")
                and kind == "header"
                and ref_type == "default"
            ):
                source = (source + "\n" + f"WATERMARK:{watermark['text']}").strip()
            rendered, missing = render_placeholders(source, context, strict=True)
            unresolved.extend(missing)
            if rendered or ref_type == "default":
                _bind_section_part(
                    sect_pr,
                    rels_root,
                    files,
                    part_name=part_name,
                    content=rendered,
                    kind=kind,
                    ref_type=ref_type,
                )
                report.changed_parts.append(f"word/{part_name}")
            if re.search(r"\{PAGE\}", source):
                report.fields_added.append("PAGE")
            if re.search(r"\{NUMPAGES\}", source):
                report.fields_added.append("NUMPAGES")

        files["word/document.xml"] = etree.tostring(
            document, xml_declaration=True, encoding="UTF-8", standalone="yes"
        )
        files["word/_rels/document.xml.rels"] = etree.tostring(
            rels_root, xml_declaration=True, encoding="UTF-8", standalone="yes"
        )
        report.changed_parts.extend(["word/document.xml", "word/_rels/document.xml.rels"])
        report.unresolved_placeholders = sorted(set(unresolved))
        report.fields_added = sorted(set(report.fields_added))

        for name, payload in files.items():
            zout.writestr(name, payload)

    return out_buf.getvalue(), report
