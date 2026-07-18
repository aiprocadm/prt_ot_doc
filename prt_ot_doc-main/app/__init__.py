"""Compatibility package exposing ``backend.app`` as top-level ``app``.

The codebase historically imports modules as ``app.*`` while some operator-facing
commands use ``backend.app.*`` from the repository root. This shim keeps both
entry styles working without forcing a risky repo-wide import rewrite.
"""

from __future__ import annotations

from pathlib import Path

_backend_app_dir = Path(__file__).resolve().parent.parent / "backend" / "app"

# Expose backend/app as the package search path for ``app.*`` imports.
__path__ = [str(_backend_app_dir)]
