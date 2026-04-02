from __future__ import annotations

import ast
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, model_validator

NODE_KINDS = {
    "render_docx",
    "apply_headers",
    "replace_dry_run",
    "replace_apply",
    "convert_pdf",
    "build_zip",
    "send_edo",
    "verify_signature",
    "notify",
    "webhook",
    "delay",
    "branch",
    "archive",
    "noop",
}

REQUIRED_CONFIG_KEYS = {
    "render_docx": {"template_code"},
    "webhook": {"url"},
    "notify": {"channel"},
    "delay": {"seconds"},
}

RESERVED_CTX_KEYS = {
    "tenant_id",
    "correlation_id",
    "job_id",
    "run_id",
    "artifacts",
    "meta",
}


class PipelineRetryPolicy(BaseModel):
    max_attempts: int = Field(default=1, ge=1, le=10)
    backoff_seconds: int = Field(default=0, ge=0, le=3600)


class PipelineNode(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    type: str
    config: dict[str, Any] = Field(default_factory=dict)
    retry: PipelineRetryPolicy = Field(default_factory=PipelineRetryPolicy)
    timeout_s: int = Field(default=300, ge=1, le=7200)
    on_error: str = Field(default="fail")
    emit_events: bool = True

    @model_validator(mode="after")
    def _validate_type(self) -> "PipelineNode":
        if self.type not in NODE_KINDS:
            raise ValueError(f"unsupported node type: {self.type}")
        required = REQUIRED_CONFIG_KEYS.get(self.type, set())
        missing = [k for k in required if k not in self.config]
        if missing:
            raise ValueError(f"node '{self.id}' missing config keys: {', '.join(sorted(missing))}")
        return self


class PipelineEdge(BaseModel):
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    condition: str | None = None


class PipelineGraph(BaseModel):
    nodes: list[PipelineNode]
    edges: list[PipelineEdge] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)


_SAFE_CALLS = {"len"}
_SAFE_BOOL_OPS = (ast.And, ast.Or)
_SAFE_COMPARE_OPS = (ast.Eq, ast.NotEq, ast.In, ast.NotIn, ast.Lt, ast.LtE, ast.Gt, ast.GtE)


def _eval_ast(node: ast.AST, ctx: dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body, ctx)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id == "ctx":
            return ctx
        raise ValueError("unsafe name in condition")
    if isinstance(node, ast.Subscript):
        value = _eval_ast(node.value, ctx)
        key = _eval_ast(node.slice, ctx)
        return value[key]
    if isinstance(node, ast.Attribute):
        value = _eval_ast(node.value, ctx)
        if node.attr.startswith("__"):
            raise ValueError("unsafe attribute access")
        return getattr(value, node.attr)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _SAFE_CALLS:
            fn = len if node.func.id == "len" else None
            if fn is None:
                raise ValueError("unsafe call in condition")
            args = [_eval_ast(arg, ctx) for arg in node.args]
            return fn(*args)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            target = _eval_ast(node.func.value, ctx)
            args = [_eval_ast(arg, ctx) for arg in node.args]
            return target.get(*args)
        raise ValueError("unsafe call in condition")
    if isinstance(node, ast.BoolOp):
        if not isinstance(node.op, _SAFE_BOOL_OPS):
            raise ValueError("unsafe bool operator")
        values = [_eval_ast(v, ctx) for v in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.Compare):
        left = _eval_ast(node.left, ctx)
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            if not isinstance(op, _SAFE_COMPARE_OPS):
                raise ValueError("unsafe compare operator")
            right = _eval_ast(comparator, ctx)
            ok = (
                left == right
                if isinstance(op, ast.Eq)
                else left != right
                if isinstance(op, ast.NotEq)
                else left in right
                if isinstance(op, ast.In)
                else left not in right
                if isinstance(op, ast.NotIn)
                else left < right
                if isinstance(op, ast.Lt)
                else left <= right
                if isinstance(op, ast.LtE)
                else left > right
                if isinstance(op, ast.Gt)
                else left >= right
            )
            if not ok:
                return False
            left = right
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval_ast(node.operand, ctx)
    if isinstance(node, ast.List):
        return [_eval_ast(el, ctx) for el in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_eval_ast(el, ctx) for el in node.elts)
    if isinstance(node, ast.Dict):
        return {_eval_ast(k, ctx): _eval_ast(v, ctx) for k, v in zip(node.keys, node.values, strict=False)}
    raise ValueError("unsafe expression")


def safe_eval_condition(expression: str, ctx: dict[str, Any]) -> bool:
    tree = ast.parse(expression, mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Lambda, ast.FunctionDef, ast.ClassDef, ast.Assign, ast.AugAssign, ast.BinOp)):
            raise ValueError("unsafe expression")
    value = _eval_ast(tree, ctx)
    return bool(value)


@dataclass(slots=True)
class GraphValidationLimits:
    max_nodes: int = 200
    max_depth: int = 200


class PipelineProfileValidator:
    def __init__(self, limits: GraphValidationLimits | None = None) -> None:
        self.limits = limits or GraphValidationLimits()

    def validate(self, graph: PipelineGraph) -> None:
        if not graph.nodes:
            raise ValueError("graph_has_no_nodes")
        if len(graph.nodes) > self.limits.max_nodes:
            raise ValueError("too_many_nodes")
        node_ids = {n.id for n in graph.nodes}
        if len(node_ids) != len(graph.nodes):
            raise ValueError("duplicate_node_id")

        incoming: dict[str, set[str]] = defaultdict(set)
        outgoing: dict[str, list[PipelineEdge]] = defaultdict(list)
        indegree = {n.id: 0 for n in graph.nodes}
        for edge in graph.edges:
            if edge.from_node not in node_ids or edge.to_node not in node_ids:
                raise ValueError("edge_references_unknown_node")
            incoming[edge.to_node].add(edge.from_node)
            outgoing[edge.from_node].append(edge)
            indegree[edge.to_node] += 1
            if edge.condition:
                safe_eval_condition(edge.condition, {"meta": {}, "artifacts": {}})

        queue = deque([nid for nid, deg in indegree.items() if deg == 0])
        visited: list[str] = []
        while queue:
            nid = queue.popleft()
            visited.append(nid)
            for edge in outgoing.get(nid, []):
                indegree[edge.to_node] -= 1
                if indegree[edge.to_node] == 0:
                    queue.append(edge.to_node)
        if len(visited) != len(node_ids):
            raise ValueError("graph_contains_cycle")

        ends = [n.id for n in graph.nodes if not outgoing.get(n.id)]
        if not ends:
            raise ValueError("graph_has_no_terminal_node")
        starts = [n.id for n in graph.nodes if not incoming.get(n.id)]
        seen = set(starts)
        queue = deque(starts)
        while queue:
            nid = queue.popleft()
            for edge in outgoing.get(nid, []):
                if edge.to_node not in seen:
                    seen.add(edge.to_node)
                    queue.append(edge.to_node)
        if seen != node_ids:
            raise ValueError("graph_has_unreachable_nodes")

        for node in graph.nodes:
            if node.type == "branch":
                if len(outgoing.get(node.id, [])) < 2:
                    raise ValueError(f"branch '{node.id}' must have at least 2 outgoing edges")
                conditioned = [e for e in outgoing.get(node.id, []) if e.condition]
                defaults = [e for e in outgoing.get(node.id, []) if not e.condition]
                if conditioned and not defaults:
                    raise ValueError(f"branch '{node.id}' has no default edge")

        self._validate_context_contract(graph)

        depth = self._max_depth(starts, outgoing)
        if depth > self.limits.max_depth:
            raise ValueError("graph_too_deep")

    def _max_depth(self, starts: list[str], outgoing: dict[str, list[PipelineEdge]]) -> int:
        best = 0
        stack = [(s, 1) for s in starts]
        while stack:
            node, depth = stack.pop()
            best = max(best, depth)
            for edge in outgoing.get(node, []):
                stack.append((edge.to_node, depth + 1))
        return best

    def _validate_context_contract(self, graph: PipelineGraph) -> None:
        # Reserved keys are controlled by orchestrator runtime and must not be redefined.
        reserved_redefined = RESERVED_CTX_KEYS.intersection(graph.inputs.keys())
        if reserved_redefined:
            keys = ", ".join(sorted(reserved_redefined))
            raise ValueError(f"graph_inputs_redefine_reserved_keys: {keys}")
