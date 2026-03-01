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
        nodes=[{"id": "branch", "type": "branch"}, {"id": "left", "type": "noop"}],
        edges=[{"from": "branch", "to": "left", "condition": "ctx.get('x') == 1"}],
    )
    with pytest.raises(ValueError, match="default"):
        PipelineProfileValidator().validate(graph)


def test_condition_engine_safe_eval() -> None:
    assert safe_eval_condition("ctx['meta']['x'] > 2 and 'pdf' in ctx['artifacts']", {"meta": {"x": 3}, "artifacts": {"pdf": "f1"}})
    with pytest.raises(ValueError):
        safe_eval_condition("__import__('os').system('echo x')", {})
