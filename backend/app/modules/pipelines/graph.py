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


def safe_eval_condition(expression: str, ctx: dict[str, Any]) -> bool:
    tree = ast.parse(expression, mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in _SAFE_CALLS:
                    raise ValueError("unsafe call in condition")
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr not in {"get"}:
                    raise ValueError("unsafe call in condition")
            else:
                raise ValueError("unsafe call in condition")
        elif isinstance(node, (ast.Import, ast.ImportFrom, ast.Lambda, ast.FunctionDef, ast.ClassDef, ast.Assign, ast.AugAssign)):
            raise ValueError("unsafe expression")
    value = eval(compile(tree, "<condition>", "eval"), {"__builtins__": {}, "len": len}, {"ctx": ctx})
    return bool(value)


@dataclass(slots=True)
class GraphValidationLimits:
    max_nodes: int = 200
    max_depth: int = 200


class PipelineProfileValidator:
    def __init__(self, limits: GraphValidationLimits | None = None) -> None:
        self.limits = limits or GraphValidationLimits()

    def validate(self, graph: PipelineGraph) -> None:
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
                conditioned = [e for e in outgoing.get(node.id, []) if e.condition]
                defaults = [e for e in outgoing.get(node.id, []) if not e.condition]
                if conditioned and not defaults:
                    raise ValueError(f"branch '{node.id}' has no default edge")

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
