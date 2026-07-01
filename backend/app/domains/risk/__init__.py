"""Deprecated compat-shim — canonical location is :mod:`app.modules.risk` (ARCH-1)."""

from __future__ import annotations

from app.modules.risk.calc import (  # noqa: F401  (compat re-export)
    rebuild_matrix_from_methodology,
    recalc_risk_map,
    score_band,
)

__all__ = ["score_band", "rebuild_matrix_from_methodology", "recalc_risk_map"]
