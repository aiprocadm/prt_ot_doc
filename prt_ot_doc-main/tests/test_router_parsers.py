from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.v1.router import _parse_json_object, _parse_replacements


def test_parse_json_object_returns_mapping() -> None:
    payload = _parse_json_object('{"a": 1}', field="context")
    assert payload == {"a": 1}


def test_parse_json_object_allows_empty_string() -> None:
    payload = _parse_json_object("   ", field="context")
    assert payload == {}


def test_parse_json_object_rejects_non_mapping() -> None:
    with pytest.raises(HTTPException) as excinfo:
        _parse_json_object("[]", field="context")
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "context must be a JSON object"


def test_parse_replacements_validates_values_are_strings() -> None:
    replacements = _parse_replacements('{"foo": "bar"}')
    assert replacements == {"foo": "bar"}


def test_parse_replacements_rejects_non_string_values() -> None:
    with pytest.raises(HTTPException) as excinfo:
        _parse_replacements('{"foo": 123}')
    assert excinfo.value.detail == "replacements values must be strings"
