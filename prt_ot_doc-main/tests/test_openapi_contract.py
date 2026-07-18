from __future__ import annotations

from pathlib import Path

import pytest
import yaml

SCHEMA_PATH = Path("docs/openapi.yaml")


def test_openapi_exists_and_valid_yaml() -> None:
    if not SCHEMA_PATH.exists():
        pytest.skip("docs/openapi.yaml not found")
    data = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    openapi_version = str(data.get("openapi", ""))
    assert openapi_version.startswith("3."), openapi_version


@pytest.mark.parametrize("rel_path", ["docs/openapi.yaml", "docs/schema/openapi.yaml"])
def test_optional_openapi_variants(rel_path: str) -> None:
    candidate = Path(rel_path)
    if not candidate.exists():
        pytest.skip(f"{rel_path} not available")
    data = yaml.safe_load(candidate.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
