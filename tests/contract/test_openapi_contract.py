from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.contract import validate


@pytest.mark.contract
def test_openapi_contract_is_valid(capsys: pytest.CaptureFixture[str]) -> None:
    spec_path = Path("docs/openapi.yaml")
    assert spec_path.exists(), "OpenAPI specification must be present in docs/openapi.yaml"

    validate.main()

    captured = capsys.readouterr().out
    payload = json.loads(captured)

    assert Path(payload["spec_path"]).name == spec_path.name
    assert payload["version"].startswith("3."), "OpenAPI version must be defined"
    assert payload["paths"] > 0
    assert payload["operations"] >= payload["paths"]
