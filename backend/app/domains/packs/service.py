"""Deprecated compat-shim — canonical location is :mod:`app.modules.packs.operations` (ARCH-1)."""

from __future__ import annotations

from app.modules.packs.operations import (  # noqa: F401  (compat re-export)
    DEFAULT_STEP_PROFILES,
    SCENARIO_ALIASES,
    PackAssembler,
    resolve_pipeline_profile,
    resolve_scenario_label,
)

__all__ = [
    "SCENARIO_ALIASES",
    "DEFAULT_STEP_PROFILES",
    "resolve_scenario_label",
    "resolve_pipeline_profile",
    "PackAssembler",
]
