from __future__ import annotations

import re
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

W = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "v": "urn:schemas-microsoft-com:vml",
}


def _compile(source: str, *, case_sensitive: bool, whole_word: bool) -> re.Pattern[str]:
    escaped = re.escape(source)
    if whole_word:
        escaped = rf"(?<![0-9A-Za-zА-Яа-яЁё_]){escaped}(?![0-9A-Za-zА-Яа-яЁё_])"
    return re.compile(escaped, 0 if case_sensitive else re.IGNORECASE)


def replace_xml_parts(
    docx_bytes: bytes, rules: list[dict], *, case_sensitive: bool, whole_word: bool
) -> tuple[bytes, list[dict]]:
    zin = ZipFile(BytesIO(docx_bytes))
    out_io = BytesIO()
    reports: list[dict] = []
    with ZipFile(out_io, "w", ZIP_DEFLATED) as zout:
        for name in zin.namelist():
            content = zin.read(name)
            if not (name.startswith("word/") and name.endswith(".xml")):
                zout.writestr(name, content)
                continue
            root = etree.fromstring(content)
            changed = False
            for node in root.xpath("//w:txbxContent//w:t | //v:textbox//w:t", namespaces=W):
                text = node.text or ""
                before = text
                for rule in rules:
                    src = str(rule.get("from", ""))
                    dst = str(rule.get("to", ""))
                    if not src:
                        continue
                    text = _compile(src, case_sensitive=case_sensitive, whole_word=whole_word).sub(
                        dst, text
                    )
                if text != before:
                    changed = True
                    reports.append(
                        {
                            "location": name,
                            "before_snippet": before[:200],
                            "after_snippet": text[:200],
                        }
                    )
                    node.text = text
            if changed:
                content = etree.tostring(
                    root, xml_declaration=True, encoding="UTF-8", standalone="yes"
                )
            zout.writestr(name, content)
    return out_io.getvalue(), reports
