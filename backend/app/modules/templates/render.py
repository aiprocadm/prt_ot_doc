from __future__ import annotations

import datetime as dt
import zipfile
from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET

from app.core.xml_security import stdlib_fromstring
from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

from .passport import inject_passport

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def _f_upper(value: Any) -> str:
    return str(value).upper()


def _f_lower(value: Any) -> str:
    return str(value).lower()


def _f_date(value: Any, fmt: str = "%Y-%m-%d") -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.strftime(fmt)
    if isinstance(value, str):
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.strftime(fmt)
        except ValueError:
            return value
    return str(value)


def _env() -> SandboxedEnvironment:
    env = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)
    env.filters.update({"upper": _f_upper, "lower": _f_lower, "date": _f_date})
    return env


def _render_jinja(text: str, data: dict[str, Any]) -> str:
    return _env().from_string(text).render(**data)


def _render_xml_part(content: bytes, data: dict[str, Any]) -> bytes:
    root = stdlib_fromstring(content)  # разд. 64.2: защита от XXE/billion-laughs
    for paragraph in root.findall(".//w:p", NS):
        text_nodes = paragraph.findall(".//w:t", NS)
        if not text_nodes:
            continue
        original = "".join(node.text or "" for node in text_nodes)
        if "{{" not in original and "{%" not in original:
            continue
        rendered = _render_jinja(original, data)
        text_nodes[0].text = rendered
        for node in text_nodes[1:]:
            node.text = ""
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def render_docx(
    template_bytes: bytes,
    data: dict[str, Any],
    passport: dict[str, Any],
    *,
    visible_passport: bool = False,
) -> bytes:
    output = BytesIO()
    with (
        zipfile.ZipFile(BytesIO(template_bytes), "r") as zin,
        zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout,
    ):
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename.startswith("word/") and item.filename.endswith(".xml"):
                content = _render_xml_part(content, data)
            zout.writestr(item, content)
    return inject_passport(output.getvalue(), passport, visible=visible_passport)
