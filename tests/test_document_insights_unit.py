"""Unit tests for document version compare / dependency helpers."""

from __future__ import annotations

from app.services.document_insights import diff_version_data_json


def test_diff_version_data_json_detects_changes() -> None:
    left = {"a": 1, "b": {"x": 1}, "c": "keep"}
    right = {"a": 2, "b": {"x": 1}, "d": 9}
    diffs = diff_version_data_json(left, right)
    fields = {d["field"]: d["change"] for d in diffs}
    assert fields["a"] == "modified"
    assert fields["d"] == "added"
    assert "c" in fields and fields["c"] == "removed"
