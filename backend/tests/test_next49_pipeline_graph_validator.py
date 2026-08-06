from __future__ import annotations

import pytest

from app.modules.pipelines.graph import PipelineGraph, PipelineProfileValidator, safe_eval_condition


def test_validator_rejects_cycle() -> None:
    graph = PipelineGraph(
        nodes=[{"id": "a", "type": "noop"}, {"id": "b", "type": "noop"}],
        edges=[{"from": "a", "to": "b"}, {"from": "b", "to": "a"}],
    )
    with pytest.raises(ValueError, match="cycle"):
        PipelineProfileValidator().validate(graph)


def test_validator_requires_default_branch() -> None:
    graph = PipelineGraph(
        nodes=[
            {"id": "branch", "type": "branch"},
            {"id": "left", "type": "noop"},
            {"id": "right", "type": "noop"},
        ],
        edges=[
            {"from": "branch", "to": "left", "condition": "ctx.get('x') == 1"},
            {"from": "branch", "to": "right", "condition": "ctx.get('x') == 2"},
        ],
    )
    with pytest.raises(ValueError, match="default"):
        PipelineProfileValidator().validate(graph)


def test_condition_engine_safe_eval() -> None:
    assert safe_eval_condition(
        "ctx['meta']['x'] > 2 and 'pdf' in ctx['artifacts']",
        {"meta": {"x": 3}, "artifacts": {"pdf": "f1"}},
    )
    with pytest.raises(ValueError):
        safe_eval_condition("__import__('os').system('echo x')", {})


def test_condition_engine_rejects_binary_math() -> None:
    with pytest.raises(ValueError, match="unsafe"):
        safe_eval_condition("ctx.get('x', 0) + 1 > 2", {"x": 1})


def test_validator_rejects_empty_graph() -> None:
    graph = PipelineGraph(nodes=[], edges=[])
    with pytest.raises(ValueError, match="no_nodes"):
        PipelineProfileValidator().validate(graph)


def test_validator_rejects_reserved_inputs_override() -> None:
    graph = PipelineGraph(
        nodes=[{"id": "start", "type": "noop"}],
        edges=[],
        inputs={"tenant_id": {"type": "string"}},
    )
    with pytest.raises(ValueError, match="reserved_keys"):
        PipelineProfileValidator().validate(graph)


def test_branch_requires_min_two_edges() -> None:
    graph = PipelineGraph(
        nodes=[{"id": "branch", "type": "branch"}, {"id": "next", "type": "noop"}],
        edges=[{"from": "branch", "to": "next"}],
    )
    with pytest.raises(ValueError, match="at least 2"):
        PipelineProfileValidator().validate(graph)
