"""Deprecated compat-shim — risk calc moved to :mod:`app.modules.risk.calc` (ARCH-1).

Kept as a re-export so ``from app.domains.risk.calc import …`` keeps working until the
next major (POST-1 removes the ``domains/*`` shims). New code should import from
``app.modules.risk``.
"""

from __future__ import annotations

from app.modules.risk.calc import (  # noqa: F401  (compat re-export)
    Band,
    _band_from_definition,
    _fallback_band,
    _scale_values,
    rebuild_matrix_from_methodology,
    recalc_risk_map,
    score_band,
)
