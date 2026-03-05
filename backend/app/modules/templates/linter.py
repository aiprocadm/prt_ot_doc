from __future__ import annotations

import re
import zipfile
from collections import Counter
from collections.abc import Iterable
from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET

PLACEHOLDER_RE = re.compile(r"{{\s*([^}]+?)\s*}}")
TAG_RE = re.compile(r"{%\s*([^%]+?)\s*%}")
FIELD_PATH_RE = re.compile(r"\b([a-zA-Z_][\w.]+)\b")
ALLOWED_WORDS = {"if", "for", "in", "True", "False", "none", "None", "and", "or", "not"}


def _iter_docx_xml(docx_bytes: bytes) -> Iterable[tuple[str, str]]:
    with zipfile.ZipFile(BytesIO(docx_bytes)) as zf:
        for name in zf.namelist():
            if name == "word/document.xml" or (
                name.startswith("word/header") and name.endswith(".xml")
            ) or (name.startswith("word/footer") and name.endswith(".xml")):
                yield name, zf.read(name).decode("utf-8", errors="ignore")


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


def _safe_expr(expr: str) -> bool:
    return bool(re.fullmatch(r"[\w\s.()=!<>\[\]\-+*/'\",:|&]+", expr))


def parse_docx_placeholders(docx_bytes: bytes) -> dict[str, Any]:
    tokens: list[dict[str, Any]] = []
    field_occurrences: Counter[str] = Counter()
    loops: list[dict[str, Any]] = []
    conditions: list[dict[str, Any]] = []

    for source, xml in _iter_docx_xml(docx_bytes):
        text = _extract_text(xml)
        for match in PLACEHOLDER_RE.finditer(text):
            expr = match.group(1).strip()
            tokens.append({"type": "placeholder", "expr": expr, "source": source, "offset": match.start()})
            for field in FIELD_PATH_RE.findall(expr):
                if field not in ALLOWED_WORDS:
                    field_occurrences[field] += 1

        for match in TAG_RE.finditer(text):
            expr = match.group(1).strip()
            tokens.append({"type": "block", "expr": expr, "source": source, "offset": match.start()})
            if expr.startswith("for ") and " in " in expr:
                var, _, it = expr[4:].partition(" in ")
                loops.append({"var": var.strip(), "iter": it.strip(), "locations": [source]})
            elif expr.startswith("if "):
                conditions.append({"expr": expr[3:].strip(), "locations": [source]})

    fields = [
        {"name": name, "occurrences": count, "locations": []}
        for name, count in sorted(field_occurrences.items())
    ]
    return {
        "fields": fields,
        "loops": loops,
        "conditions": conditions,
        "raw_tokens": tokens,
    }


def lint_template(docx_bytes: bytes, *, required_fields: list[str] | None = None) -> dict[str, Any]:
    parsed = parse_docx_placeholders(docx_bytes)
    errors: list[str] = []
    warnings: list[str] = []
    stack: list[str] = []

    for token in parsed["raw_tokens"]:
        if token["type"] != "block":
            continue
        expr: str = token["expr"]
        if expr.startswith("if "):
            stack.append("if")
            if not _safe_expr(expr[3:].strip()):
                errors.append(f"Unsafe if expression: {expr}")
        elif expr == "endif":
            if not stack or stack[-1] != "if":
                errors.append("Unexpected endif")
            else:
                stack.pop()
        elif expr.startswith("for ") and " in " in expr:
            stack.append("for")
            body = expr[4:]
            var, _, iterable = body.partition(" in ")
            if not re.fullmatch(r"[a-zA-Z_][\w]*", var.strip()):
                errors.append(f"Invalid for variable: {expr}")
            if not _safe_expr(iterable.strip()):
                errors.append(f"Unsafe for iterable expression: {expr}")
        elif expr == "endfor":
            if not stack or stack[-1] != "for":
                errors.append("Unexpected endfor")
            else:
                stack.pop()
        else:
            errors.append(f"Unknown directive: {expr}")

    if stack:
        errors.append("Unclosed blocks: " + ", ".join(stack))

    found_fields = [item["name"] for item in parsed["fields"]]
    if required_fields:
        for name in required_fields:
            if name not in found_fields:
                warnings.append(f"Required field is not used in template: {name}")

    return {
        "found_fields": found_fields,
        "blocks": {
            "loops": parsed["loops"],
            "conditions": parsed["conditions"],
        },
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "field_count": len(parsed["fields"]),
            "loop_count": len(parsed["loops"]),
            "condition_count": len(parsed["conditions"]),
            "error_count": len(errors),
            "warning_count": len(warnings),
        },
        "placeholders_json": {
            "fields": parsed["fields"],
            "loops": parsed["loops"],
            "conditions": parsed["conditions"],
        },
    }
