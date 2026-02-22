from __future__ import annotations

import re
import zipfile
from collections.abc import Iterable
from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET

PLACEHOLDER_RE = re.compile(r"{{\s*([^}]+?)\s*}}")
BLOCK_RE = re.compile(r"{%\s*(if|for|endif|endfor)\b([^%}]*)%}")
FIELD_PATH_RE = re.compile(r"\b([a-zA-Z_][\w.]+)\b")


def _iter_docx_xml(docx_bytes: bytes) -> Iterable[str]:
    with zipfile.ZipFile(BytesIO(docx_bytes)) as zf:
        for name in zf.namelist():
            if name == "word/document.xml" or (
                name.startswith("word/header") and name.endswith(".xml")
            ) or (name.startswith("word/footer") and name.endswith(".xml")):
                yield zf.read(name).decode("utf-8", errors="ignore")


def _extract_text(xml_text: str) -> str:
    root = ET.fromstring(xml_text)
    paragraphs: list[str] = []
    for p in root.iter():
        if not p.tag.endswith("}p"):
            continue
        runs: list[str] = []
        for node in p.iter():
            if node.tag.endswith("}t") and node.text:
                runs.append(node.text)
        if runs:
            paragraphs.append("".join(runs))
    return "\n".join(paragraphs)


def lint_template(docx_bytes: bytes) -> dict[str, Any]:
    texts: list[str] = []
    for xml in _iter_docx_xml(docx_bytes):
        texts.append(_extract_text(xml))

    merged = "\n".join(texts)
    placeholders = [m.group(1).strip() for m in PLACEHOLDER_RE.finditer(merged)]

    blocks: list[dict[str, str]] = []
    stack: list[str] = []
    errors: list[str] = []
    for m in BLOCK_RE.finditer(merged):
        token = m.group(1)
        expr = (m.group(2) or "").strip()
        blocks.append({"type": token, "expr": expr})
        if token in {"if", "for"}:
            stack.append(token)
        elif token == "endif":
            if not stack or stack[-1] != "if":
                errors.append("Unexpected endif")
            else:
                stack.pop()
        elif token == "endfor":
            if not stack or stack[-1] != "for":
                errors.append("Unexpected endfor")
            else:
                stack.pop()
    if stack:
        errors.append("Unclosed blocks: " + ", ".join(stack))

    field_paths: set[str] = set()
    for ph in placeholders:
        for c in FIELD_PATH_RE.findall(ph):
            if c not in {"if", "for", "in", "True", "False", "none", "None"}:
                field_paths.add(c)
    for block in blocks:
        for c in FIELD_PATH_RE.findall(block.get("expr", "")):
            if c not in {"if", "for", "in", "True", "False", "none", "None"}:
                field_paths.add(c)

    return {
        "placeholders": sorted(set(placeholders)),
        "blocks": blocks,
        "field_paths": sorted(field_paths),
        "stats": {
            "placeholder_count": len(placeholders),
            "block_count": len(blocks),
        },
        "errors": errors,
    }
