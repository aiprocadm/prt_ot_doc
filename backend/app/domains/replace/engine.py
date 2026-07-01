"""Deprecated compat-shim — canonical location is :mod:`app.modules.replace.legacy_engine` (ARCH-1).

The legacy persisted ``ReplaceEngine`` moved under a new name because the richer
``app.modules.replace.engine`` (the pattern-replacement canon) already owns ``engine.py``.
"""

from __future__ import annotations

from app.modules.replace.legacy_engine import (  # noqa: F401  (compat re-export)
    ReplaceEngine,
    ReplacePatch,
)

__all__ = ["ReplaceEngine", "ReplacePatch"]
