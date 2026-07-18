"""Static guard against the in-place JSON-column mutation bug class.

Background
----------
~169 ORM columns in ``backend/app/models/*.py`` are declared as
``mapped_column(JSON)`` / ``mapped_column(JSONBType)`` and NONE are wrapped in
:class:`sqlalchemy.ext.mutable.MutableDict` / ``MutableList``. With SQLAlchemy's
default change detection an attribute is only flagged dirty when a *new object*
(different identity) is assigned to it. Therefore mutating such a column
in place and NOT reassigning a fresh object silently loses the change on
flush/commit::

    run.outputs["stages"][stage] = entry      # in-place, never reassigned -> LOST
    record.payload_json.update({"k": v})       # in-place -> LOST

The safe idiom — used consistently across the codebase — copies first, then
reassigns a *different* object::

    outputs = dict(run.outputs or {})
    outputs["stages"] = {...}
    run.outputs = outputs                      # fresh object -> dirty -> persisted

This was the root cause of the already-fixed ``PipelineService._record_stage``
bug (``PipelineRun.outputs["stages"]`` came back ``{}`` after ``session.refresh``).

What this test does
-------------------
A pure-AST scan (no app import — runs on any Python) over the runtime layers.
It flags any ``<receiver>.<json_field>[...] = ...`` subscript-assign or
``<receiver>.<json_field>.<mutator>(...)`` call on a *distinctive* JSON-column
attribute name, UNLESS the same function later reassigns ``<receiver>.<json_field>``
to a fresh object. This catches a careless ``obj.json_field["k"] = v`` before it
silently ships.

The field list is deliberately restricted to *distinctive* column names
(mostly ``*_json`` / multi-word) so the receiver is almost certainly an ORM
instance — generic names like ``payload``/``headers``/``meta``/``context`` are
excluded to avoid false positives on local dicts and Starlette objects.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Distinctive JSON-column attribute names. Generic names (payload, headers,
# meta, config, context, details, summary, action, input, output, steps,
# conditions, tags, settings, limits, features, recipients, schedule, ...) are
# intentionally OMITTED: they frequently name local dicts / Pydantic models /
# Starlette response objects, which would cause false positives.
JSON_FIELDS: frozenset[str] = frozenset(
    {
        "outputs",
        "result_metadata",
        "result_json",
        "payload_json",
        "metadata_json",
        "error_payload",
        "error_payload_json",
        "render_log",
        "source_refs",
        "compliance_refs",
        "data_json",
        "steps_json",
        "stats_json",
        "scope_json",
        "scopes_json",
        "answers_json",
        "materials_json",
        "mapping_json",
        "options_json",
        "conditions_json",
        "rules_json",
        "qc_report_json",
        "verification_result_json",
        "changed_fields",
        "last_error",
        "recommendations_json",
        "findings_json",
        "causes_json",
        "company_snapshot",
        "pipeline_steps_json",
        "required_inputs_json",
        "recommended_measures",
        "branding_payload",
        "external_runtime_state",
        "completion_payload",
        "provider_payload",
        "signature_payload",
        "correct_answer_json",
        "preview_json",
        "compatibility_json",
        "dependency_json",
        "linter_report_json",
        "placeholder_index",
        "tags_json",
        "headers_json",
        "delivery_history_json",
        "request_payload_json",
        "response_payload_json",
        "raw_payload_json",
        "input_payload_json",
        "output_payload_json",
        "before_json",
        "after_json",
        "resource_attrs",
        "retention_policy",
        "integration_keys",
    }
)

MUTATORS: frozenset[str] = frozenset(
    {"append", "extend", "update", "setdefault", "pop", "popitem", "insert", "clear"}
)

# Receivers that are never ORM instances even if the attribute name collides.
DENY_RECEIVERS: frozenset[str] = frozenset({"response", "request", "self.cache", "env"})


def _attr_path(node: ast.AST) -> str | None:
    """Best-effort dotted path for an Attribute/Name node ("run.outputs")."""
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive
        return None


def _is_orm_like_receiver(recv: ast.expr) -> bool:
    """Heuristic: receiver looks like a runtime instance, not a model class /
    denied object. ``DocumentVersion.data_json`` (column expression) has an
    uppercase root Name and is excluded."""
    path = _attr_path(recv)
    if path is None:
        return False
    if path in DENY_RECEIVERS:
        return False
    root = path.split(".", 1)[0]
    # Column expressions like `Model.field[...]` use a Capitalized class root.
    if root[:1].isupper():
        return False
    return True


class _FunctionScanner(ast.NodeVisitor):
    """Scan a single function body for unsafe in-place JSON mutations."""

    def __init__(self) -> None:
        self.reassigned: set[tuple[str, str]] = set()
        self.violations: list[tuple[int, str]] = []

    def collect(self, func: ast.AST) -> None:
        # Pass 1: record every `<receiver>.<field> = <fresh object>` reassignment.
        # A self-reassign (`x.f = x.f`) assigns the SAME object and does NOT mark
        # the attribute dirty, so it is deliberately NOT recorded as safe.
        for node in ast.walk(func):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Attribute) and tgt.attr in JSON_FIELDS:
                        recv = _attr_path(tgt.value)
                        if recv is None:
                            continue
                        if _attr_path(node.value) == f"{recv}.{tgt.attr}":
                            continue  # same-object self-reassign -> not dirty
                        self.reassigned.add((recv, tgt.attr))
        # Pass 2: find in-place mutations not covered by a reassignment.
        for node in ast.walk(func):
            self._check_subscript_assign(node)
            self._check_method_mutation(node)

    def _flag(self, attr: ast.Attribute, line: int, kind: str) -> None:
        if attr.attr not in JSON_FIELDS:
            return
        if not _is_orm_like_receiver(attr.value):
            return
        recv = _attr_path(attr.value)
        if recv is None:
            return
        if (recv, attr.attr) in self.reassigned:
            return  # fresh reassignment present in same function -> safe
        self.violations.append((line, f"{kind}: {recv}.{attr.attr}"))

    def _check_subscript_assign(self, node: ast.AST) -> None:
        # `<recv>.<field>[...] = ...`, nested `<recv>.<field>[a][b] = ...`,
        # or augmented `<recv>.<field>[...] += ...`.
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        for tgt in targets:
            if not isinstance(tgt, ast.Subscript):
                continue
            # Descend through a chain of subscripts to the base container.
            base: ast.expr = tgt
            while isinstance(base, ast.Subscript):
                base = base.value
            if isinstance(base, ast.Attribute):
                self._flag(base, tgt.lineno, "subscript-assign")

    def _check_method_mutation(self, node: ast.AST) -> None:
        # `<recv>.<field>.<mutator>(...)`
        if not isinstance(node, ast.Call):
            return
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in MUTATORS
            and isinstance(func.value, ast.Attribute)
        ):
            self._flag(func.value, node.lineno, f"{func.attr}()")


def scan_source(source: str) -> list[tuple[int, str]]:
    """Return list of (lineno, description) violations in a source string."""
    tree = ast.parse(source)
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scanner = _FunctionScanner()
            scanner.collect(node)
            violations.extend(scanner.violations)
    return violations


# --------------------------------------------------------------------------- #
# Unit tests for the detector itself (proves it has teeth).                    #
# --------------------------------------------------------------------------- #

_BAD_SUBSCRIPT = """
async def handler(session, run):
    run.outputs["stages"] = {}
    await session.commit()
"""

_BAD_NESTED = """
async def handler(session, run):
    run.outputs["stages"][key] = entry
    await session.commit()
"""

_BAD_METHOD = """
async def handler(session, record):
    record.payload_json.update({"k": v})
    await session.commit()
"""

_BAD_SELF_REASSIGN = """
async def handler(session, run):
    run.result_metadata["k"] = v
    run.result_metadata = run.result_metadata  # same object -> still not dirty
    await session.commit()
"""

_SAFE_COPY_REASSIGN = """
async def handler(session, run):
    outputs = dict(run.outputs or {})
    outputs["stages"] = {"x": 1}
    run.outputs = outputs
    await session.commit()
"""

_SAFE_LOCAL_VAR = """
def build():
    outputs = {}
    outputs["stages"] = {}          # bare local Name, not an attribute
    return outputs
"""

_SAFE_COLUMN_EXPR = """
def query():
    return select(M).where(DocumentVersion.data_json["k"].astext == "v")
"""

_SAFE_RESPONSE_HEADERS = """
def view(response):
    response.headers_json.update({"x": "y"})   # denied receiver
"""


@pytest.mark.parametrize(
    "src",
    [_BAD_SUBSCRIPT, _BAD_NESTED, _BAD_METHOD, _BAD_SELF_REASSIGN],
    ids=["subscript", "nested", "method", "self-reassign"],
)
def test_detector_flags_unsafe_mutation(src: str) -> None:
    assert scan_source(src), "detector should flag in-place JSON mutation"


@pytest.mark.parametrize(
    "src",
    [_SAFE_COPY_REASSIGN, _SAFE_LOCAL_VAR, _SAFE_COLUMN_EXPR, _SAFE_RESPONSE_HEADERS],
    ids=["copy-reassign", "local-var", "column-expr", "response-headers"],
)
def test_detector_allows_safe_patterns(src: str) -> None:
    assert scan_source(src) == [], "detector must not flag safe patterns"


# --------------------------------------------------------------------------- #
# Integration: the real runtime tree must be clean.                            #
# --------------------------------------------------------------------------- #

_APP_ROOT = Path(__file__).resolve().parent.parent / "backend" / "app"
_SCANNED_LAYERS = ("services", "modules", "domains", "api", "tasks", "celery", "core")


def _runtime_files() -> list[Path]:
    files: list[Path] = []
    for layer in _SCANNED_LAYERS:
        root = _APP_ROOT / layer
        if root.is_dir():
            files.extend(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    return files


def test_no_inplace_json_mutation_in_runtime_layers() -> None:
    offenders: list[str] = []
    for path in _runtime_files():
        source = path.read_text(encoding="utf-8")
        for lineno, desc in scan_source(source):
            rel = path.relative_to(_APP_ROOT.parent.parent)
            offenders.append(f"{rel}:{lineno}  {desc}")
    assert not offenders, (
        "In-place mutation of a JSON column without fresh reassignment "
        "(silently lost on flush/commit — wrap the change in a copy and "
        "reassign a new object, e.g. `obj.field = {**obj.field, ...}`):\n" + "\n".join(offenders)
    )
