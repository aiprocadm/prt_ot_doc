from __future__ import annotations

import base64
import json
import zipfile
from io import BytesIO
from typing import Any

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
CP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
FMTID = "{D5CDD505-2E9C-101B-9397-08002B2CF9AE}"


def _hidden_passport_paragraph(passport: dict[str, Any], *, visible: bool) -> str:
    payload_json = json.dumps(passport, ensure_ascii=False, sort_keys=True)
    payload = base64.b64encode(payload_json.encode("utf-8")).decode("ascii")
    if visible:
        return (
            f'<w:p xmlns:w="{W_NS}"><w:r><w:t>PTD-PASSPORT-VISIBLE:{payload_json}</w:t></w:r></w:p>'
        )
    return (
        f'<w:p xmlns:w="{W_NS}"><w:r><w:rPr><w:vanish/></w:rPr>'
        f"<w:t>PTD-PASSPORT:{payload}</w:t></w:r></w:p>"
    )


def inject_passport(docx_bytes: bytes, passport: dict[str, Any], *, visible: bool = False) -> bytes:
    out = BytesIO()
    with zipfile.ZipFile(BytesIO(docx_bytes), "r") as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        names = set(zin.namelist())
        content_types_xml: str | None = None
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                txt = data.decode("utf-8", errors="ignore")
                txt = txt.replace("</w:body>", f"{_hidden_passport_paragraph(passport, visible=visible)}</w:body>")
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

        if content_types_xml is not None:
            if "docProps/custom.xml" not in content_types_xml:
                override = '<Override PartName="/docProps/custom.xml" ContentType="application/vnd.openxmlformats-officedocument.custom-properties+xml"/>'
                content_types_xml = content_types_xml.replace("</Types>", override + "</Types>")
            zout.writestr("[Content_Types].xml", content_types_xml.encode("utf-8"))

    return out.getvalue()
