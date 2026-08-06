"""Pin test for RB-002e — only `api` service should run alembic upgrade."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "docker-compose.yml"


@pytest.fixture(scope="module")
def compose_config() -> dict:
    with COMPOSE_FILE.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _env_map(service: dict) -> dict[str, str]:
    """Normalize compose `environment` (list or dict) into a dict."""
    env = service.get("environment", {})
    if isinstance(env, list):
        return dict(item.split("=", 1) for item in env if "=" in item)
    return {str(k): str(v) for k, v in env.items()}


def test_api_service_does_not_disable_migrations(compose_config: dict) -> None:
    """`api` MUST keep the entrypoint default (RUN_MIGRATIONS=true)."""
    api_env = _env_map(compose_config["services"]["api"])
    assert (
        api_env.get("RUN_MIGRATIONS", "true") == "true"
    ), "api service must run migrations — leave RUN_MIGRATIONS unset or 'true'"


def test_worker_service_disables_migrations(compose_config: dict) -> None:
    """`worker` MUST NOT run migrations (RB-002e race fix)."""
    worker_env = _env_map(compose_config["services"]["worker"])
    assert (
        worker_env.get("RUN_MIGRATIONS") == "false"
    ), "worker service must set RUN_MIGRATIONS=false to avoid alembic race with api"


def test_beat_service_disables_migrations(compose_config: dict) -> None:
    """`beat` MUST NOT run migrations (RB-002e race fix)."""
    beat_env = _env_map(compose_config["services"]["beat"])
    assert (
        beat_env.get("RUN_MIGRATIONS") == "false"
    ), "beat service must set RUN_MIGRATIONS=false to avoid alembic race with api"
