"""Pin test for RB-002f — perf-smoke ci.yml must seed admin-bootstrap env vars."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CI_YAML = ROOT / ".github" / "workflows" / "ci.yml"

REQUIRED_KEYS = (
    "ADMIN_BOOTSTRAP",
    "ADMIN_PASSWORD",
    "ADMIN_TENANT",
    "APP_ENV",
    "RATE_LIMIT_ENABLED",
)


@pytest.fixture(scope="module")
def perf_smoke_env_block() -> str:
    """Extract the perf-smoke `Fill required CI secrets` here-doc content."""
    text = CI_YAML.read_text(encoding="utf-8")
    # Find the perf-smoke job, then the env here-doc inside it.
    perf_smoke_idx = text.find("\n  perf-smoke:")
    assert perf_smoke_idx != -1, "perf-smoke job not found in ci.yml"
    perf_smoke_block = text[perf_smoke_idx:]
    match = re.search(
        r"cat >> \.env <<'EOF'(.*?)EOF",
        perf_smoke_block,
        re.DOTALL,
    )
    assert match is not None, (
        "perf-smoke `cat >> .env <<'EOF' ... EOF` block not found"
    )
    return match.group(1)


@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_perf_smoke_env_contains_admin_bootstrap_key(
    key: str, perf_smoke_env_block: str
) -> None:
    """Each required key must appear with a non-empty RHS in the here-doc."""
    pattern = rf"^\s*{re.escape(key)}=\S+"
    assert re.search(pattern, perf_smoke_env_block, re.MULTILINE), (
        f"perf-smoke env block must set {key}=<non-empty>; "
        "see RB-002f, dev_bootstrap.bootstrap_admin_user skip conditions."
    )
