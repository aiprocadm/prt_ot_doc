from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

CP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
FMTID = "{D5CDD505-2E9C-101B-9397-08002B2CF9AE}"


def build_passport(
    *,
    tenant_id: str,
    user: str,
    template_version: str,
    input_hash: str,
    correlation_id: str,
    npa_binding_id: str | None,
    document_id: str | None,
    version_id: str | None,
    version_number: int | None,
) -> dict[str, Any]:
    return {
        "template_version": template_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": user,
        "tenant_id": tenant_id,
        "sha256_input": input_hash,
        "npa_binding_id": npa_binding_id,
        "correlation_id": correlation_id,
        "document_id": document_id,
        "document_version_id": version_id,
        "version_number": version_number,
    }


def _passport_rows(passport: dict[str, Any]) -> str:
    rows = []
    for key, val in passport.items():
        value = "" if val is None else str(val)
        rows.append(
            f"<w:tr><w:tc><w:p><w:r><w:t>{key}</w:t></w:r></w:p></w:tc>"
            f"<w:tc><w:p><w:r><w:t>{value}</w:t></w:r></w:p></w:tc></w:tr>"
        )
    return "".join(rows)


def _visible_block(passport: dict[str, Any]) -> str:
    return (
        '<w:p><w:r><w:t>Document passport</w:t></w:r></w:p>'
        '<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr>'
        f"{_passport_rows(passport)}"
        '</w:tbl>'
    )


def _hidden_paragraph(passport: dict[str, Any]) -> str:
    payload_json = json.dumps(passport, ensure_ascii=False, sort_keys=True)
    return (
        f'<w:p><w:r><w:rPr><w:vanish/></w:rPr><w:t>PTD-PASSPORT:{payload_json}</w:t></w:r></w:p>'
        f'<w:p><w:r><w:t>PTD-PASSPORT:{payload_json}</w:t></w:r></w:p>'
    )


def embed_passport_docx(
    docx_path: str,
    passport: dict[str, Any],
    *,
    visible: bool,
    qr_url: str | None = None,
) -> None:
    _ = qr_url
    in_bytes = BytesIO(open(docx_path, "rb").read())
    out = BytesIO()
    with zipfile.ZipFile(in_bytes, "r") as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        content_types_xml: str | None = None
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                txt = data.decode("utf-8", errors="ignore")
                block = _hidden_paragraph(passport)
                if visible:
                    block = block + _visible_block(passport)
                if "</w:body>" in txt:
                    txt = txt.replace("</w:body>", f"{block}</w:body>")
                else:
                    block_ns0 = block.replace("w:", "ns0:")
                    txt = txt.replace("</ns0:body>", f"{block_ns0}</ns0:body>")
                data = txt.encode("utf-8")
            elif item.filename == "[Content_Types].xml":
                content_types_xml = data.decode("utf-8", errors="ignore")
                continue
            zout.writestr(item, data)

        passport_json = json.dumps(passport, ensure_ascii=False, sort_keys=True)
        custom_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="{CP_NS}" xmlns:vt="{VT_NS}">
  <property fmtid="{FMTID}" pid="2" name="passport_json"><vt:lpwstr>{passport_json}</vt:lpwstr></property>
</Properties>'''.encode("utf-8")
        zout.writestr("docProps/custom.xml", custom_xml)

        marker_payload = f"PTD-PASSPORT:{passport_json} w:vanish".encode("utf-8")
        zout.writestr(zipfile.ZipInfo("docProps/passport.txt"), marker_payload, compress_type=zipfile.ZIP_STORED)

        if content_types_xml is not None:
            if "docProps/custom.xml" not in content_types_xml:
                override = '<Override PartName="/docProps/custom.xml" ContentType="application/vnd.openxmlformats-officedocument.custom-properties+xml"/>'
                content_types_xml = content_types_xml.replace("</Types>", override + "</Types>")
            zout.writestr("[Content_Types].xml", content_types_xml.encode("utf-8"))

    with open(docx_path, "wb") as fh:
        fh.write(out.getvalue())
