from __future__ import annotations

import re
import zipfile
from collections import Counter
from collections.abc import Iterable
from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET

PLACEHOLDER_RE = re.compile(r"{{\s*(.*?)\s*}}", re.DOTALL)
TAG_RE = re.compile(r"{%\s*(.*?)\s*%}", re.DOTALL)
FIELD_PATH_RE = re.compile(r"\b([a-zA-Z_][\w.]*)\b")
FILTER_RE = re.compile(r"\|\s*([a-zA-Z_][\w]*)")
ALLOWED_WORDS = {"if", "for", "in", "True", "False", "none", "None", "and", "or", "not"}

# Filters bundled with the SandboxedEnvironment in render.py plus the Jinja2 builtins
# that are safe and commonly used in our DOCX templates. Used to warn about typos
# (e.g. `{{ name | upperr }}`) before runtime errors hit the user.
KNOWN_FILTERS: frozenset[str] = frozenset(
    {
        # Custom filters wired in render.py
        "upper",
        "lower",
        "date",
        # Jinja2 builtins kept for templates
        "default",
        "length",
        "title",
        "capitalize",
        "trim",
        "round",
        "abs",
        "int",
        "float",
        "string",
        "list",
        "first",
        "last",
        "join",
        "replace",
        "safe",
        "escape",
        "e",
    }
)


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
    # Reject dunder access patterns even when each character is in the regex
    # whitelist — `__import__('os')` would otherwise sneak through. Jinja2's
    # SandboxedEnvironment also blocks this at render time; the lint check is
    # defense in depth.
    if "__" in expr:
        return False
    return bool(re.fullmatch(r"[\w\s.()=!<>\[\]\-+*/'\",:|&]+", expr))


def _root_field(path: str) -> str:
    return path.split(".", 1)[0].split("[", 1)[0]


def _flatten_schema_keys(schema: Any, prefix: str = "") -> set[str]:
    """Flatten a sample schema/dict-of-dicts into dotted paths like `employee.name`."""

    keys: set[str] = set()
    if isinstance(schema, dict):
        for key, value in schema.items():
            if not isinstance(key, str):
                continue
            dotted = f"{prefix}.{key}" if prefix else key
            keys.add(dotted)
            if isinstance(value, (dict, list)):
                keys.update(_flatten_schema_keys(value, dotted))
    elif isinstance(schema, list):
        for item in schema:
            keys.update(_flatten_schema_keys(item, prefix))
    return keys


def parse_docx_placeholders(docx_bytes: bytes) -> dict[str, Any]:
    tokens: list[dict[str, Any]] = []
    field_occurrences: Counter[str] = Counter()
    field_locations: dict[str, list[dict[str, int]]] = {}
    loops: list[dict[str, Any]] = []
    conditions: list[dict[str, Any]] = []
    filters_used: Counter[str] = Counter()
    empty_placeholders: list[dict[str, Any]] = []
    duplicate_signatures: Counter[str] = Counter()

    for source, xml in _iter_docx_xml(docx_bytes):
        text = _extract_text(xml)
        for match in PLACEHOLDER_RE.finditer(text):
            expr = match.group(1).strip()
            tokens.append({"type": "placeholder", "expr": expr, "source": source, "offset": match.start()})
            if not expr:
                empty_placeholders.append({"source": source, "offset": match.start()})
                continue
            duplicate_signatures[expr] += 1
            for field in FIELD_PATH_RE.findall(expr):
                if field not in ALLOWED_WORDS:
                    field_occurrences[field] += 1
                    field_locations.setdefault(field, []).append({"source": source, "offset": match.start()})
            for filt in FILTER_RE.findall(expr):
                filters_used[filt] += 1

        for match in TAG_RE.finditer(text):
            expr = match.group(1).strip()
            tokens.append({"type": "block", "expr": expr, "source": source, "offset": match.start()})
            if expr.startswith("for ") and " in " in expr:
                var, _, it = expr[4:].partition(" in ")
                loops.append(
                    {
                        "var": var.strip(),
                        "iter": it.strip(),
                        "locations": [{"source": source, "offset": match.start()}],
                    }
                )
            elif expr.startswith("if "):
                conditions.append(
                    {
                        "expr": expr[3:].strip(),
                        "locations": [{"source": source, "offset": match.start()}],
                    }
                )

    fields = [
        {"name": name, "occurrences": count, "locations": []}
        for name, count in sorted(field_occurrences.items())
    ]
    for item in fields:
        item["locations"] = field_locations.get(item["name"], [])

    duplicates = [
        {"expr": expr, "count": count}
        for expr, count in sorted(duplicate_signatures.items())
        if count >= 2
    ]

    return {
        "fields": fields,
        "loops": loops,
        "conditions": conditions,
        "raw_tokens": tokens,
        "filters": [
            {"name": name, "occurrences": count}
            for name, count in sorted(filters_used.items())
        ],
        "empty_placeholders": empty_placeholders,
        "duplicates": duplicates,
    }


def lint_template(
    docx_bytes: bytes,
    *,
    required_fields: list[str] | None = None,
    sample_schema: dict[str, Any] | None = None,
    known_filters: Iterable[str] | None = None,
) -> dict[str, Any]:
    parsed = parse_docx_placeholders(docx_bytes)
    errors: list[str] = []
    warnings: list[str] = []
    stack: list[str] = []
    loop_vars: set[str] = set()

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
            var_name = var.strip()
            if not re.fullmatch(r"[a-zA-Z_][\w]*", var_name):
                errors.append(f"Invalid for variable: {expr}")
            else:
                loop_vars.add(var_name)
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

    for entry in parsed["empty_placeholders"]:
        errors.append(
            f"Empty placeholder at offset {entry['offset']} in {entry['source']}"
        )

    for dup in parsed["duplicates"]:
        if dup["count"] >= 3:
            warnings.append(
                f"Placeholder '{{{{ {dup['expr']} }}}}' used {dup['count']} times — consider a loop"
            )

    allowed_filters = set(KNOWN_FILTERS)
    if known_filters:
        allowed_filters.update(known_filters)
    for filt in parsed["filters"]:
        if filt["name"] not in allowed_filters:
            warnings.append(
                f"Unknown filter '|{filt['name']}' used {filt['occurrences']} time(s) — typo or missing registration?"
            )

    found_fields = [item["name"] for item in parsed["fields"]]

    legacy_field_paths = set(found_fields)
    for condition in parsed["conditions"]:
        for field in FIELD_PATH_RE.findall(condition["expr"]):
            if field not in ALLOWED_WORDS:
                legacy_field_paths.add(field)
    for loop in parsed["loops"]:
        for field in FIELD_PATH_RE.findall(loop["iter"]):
            if field not in ALLOWED_WORDS and field != loop["var"]:
                legacy_field_paths.add(field)
    if required_fields:
        for name in required_fields:
            if name not in found_fields:
                warnings.append(f"Required field is not used in template: {name}")

    undefined_variables: list[str] = []
    unused_variables: list[str] = []
    if sample_schema is not None:
        schema_paths = _flatten_schema_keys(sample_schema)
        schema_roots = {key.split(".", 1)[0] for key in schema_paths}
        for field in found_fields:
            root = _root_field(field)
            if root in loop_vars:
                continue
            if field in schema_paths:
                continue
            if root in schema_roots:
                # Root is provided but the deeper attribute is not — surface as undefined
                # only when the dotted path is missing entirely.
                if field not in schema_paths and "." in field:
                    undefined_variables.append(field)
                continue
            undefined_variables.append(field)
        used_roots = {_root_field(name) for name in found_fields}
        for path in sorted(schema_paths):
            root = path.split(".", 1)[0]
            if root not in used_roots:
                unused_variables.append(path)
        for undef in undefined_variables:
            warnings.append(f"Undefined variable: {undef}")

    return {
        "found_fields": found_fields,
        # Backward-compatible aliases used by older tests/callers.
        "placeholders": found_fields,
        "field_paths": sorted(legacy_field_paths),
        "blocks": {
            "loops": parsed["loops"],
            "conditions": parsed["conditions"],
        },
        "filters": parsed["filters"],
        "duplicates": parsed["duplicates"],
        "empty_placeholders": parsed["empty_placeholders"],
        "undefined_variables": undefined_variables,
        "unused_variables": unused_variables,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "field_count": len(parsed["fields"]),
            "loop_count": len(parsed["loops"]),
            "condition_count": len(parsed["conditions"]),
            "filter_count": len(parsed["filters"]),
            "duplicate_count": len(parsed["duplicates"]),
            "empty_placeholder_count": len(parsed["empty_placeholders"]),
            "error_count": len(errors),
            "warning_count": len(warnings),
            "undefined_variable_count": len(undefined_variables),
            "unused_variable_count": len(unused_variables),
        },
        "placeholders_json": {
            "fields": parsed["fields"],
            "loops": parsed["loops"],
            "conditions": parsed["conditions"],
            "filters": parsed["filters"],
            "duplicates": parsed["duplicates"],
        },
    }


def inspect_template_context(
    docx_bytes: bytes,
    *,
    available_variables: dict[str, Any] | None = None,
    required_fields: list[str] | None = None,
    known_filters: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Variable inspector: cross-check a template against an available-variable schema.

    Returns:
        - ``available``: full list of available dotted paths (sorted).
        - ``used``: dotted paths actually referenced by the template.
        - ``undefined``: used paths missing from the schema.
        - ``unused``: schema paths the template never references.
        - ``required_missing``: required_fields entries not used in the template.
        - ``filters``: filters used in template (with usage counts).
        - ``unknown_filters``: filters used but not in the allowed set.
        - ``loops`` / ``conditions``: structural information for IDE-style inspectors.
        - ``summary``: numeric overview keyed by the lists above.
    """

    schema = available_variables or {}
    parsed = parse_docx_placeholders(docx_bytes)
    available_paths = sorted(_flatten_schema_keys(schema))
    schema_path_set = set(available_paths)
    schema_roots = {path.split(".", 1)[0] for path in available_paths}
    used_paths = [item["name"] for item in parsed["fields"]]
    loop_vars = {loop["var"] for loop in parsed["loops"]}

    undefined: list[str] = []
    for field in used_paths:
        root = _root_field(field)
        if root in loop_vars:
            continue
        if field in schema_path_set:
            continue
        if root in schema_roots:
            if "." in field and field not in schema_path_set:
                undefined.append(field)
            continue
        undefined.append(field)

    used_roots = {_root_field(name) for name in used_paths}
    unused = [path for path in available_paths if path.split(".", 1)[0] not in used_roots]

    required_missing: list[str] = []
    if required_fields:
        required_missing = [name for name in required_fields if name not in used_paths]

    allowed_filters = set(KNOWN_FILTERS)
    if known_filters:
        allowed_filters.update(known_filters)
    unknown_filters = [
        item["name"] for item in parsed["filters"] if item["name"] not in allowed_filters
    ]

    return {
        "available": available_paths,
        "used": used_paths,
        "undefined": undefined,
        "unused": unused,
        "required_missing": required_missing,
        "filters": parsed["filters"],
        "unknown_filters": unknown_filters,
        "loops": parsed["loops"],
        "conditions": parsed["conditions"],
        "summary": {
            "available_count": len(available_paths),
            "used_count": len(used_paths),
            "undefined_count": len(undefined),
            "unused_count": len(unused),
            "required_missing_count": len(required_missing),
            "unknown_filter_count": len(unknown_filters),
        },
    }
