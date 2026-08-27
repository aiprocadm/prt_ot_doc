"""Packs bounded context (canonical home — ARCH-1).

Logic lives in submodules imported directly (``assets`` / ``context`` /
``definitions`` / ``seeder`` — provisioning and rendering-context helpers;
``fields`` / ``readiness`` / ``scenario_preview`` — pure wizard/readiness
logic (no DB, no FastAPI); ``operations`` — scenario-profile resolution +
``PackAssembler``; ``service`` / ``schemas`` / ``api`` — pack-run services and
the v2 router). The legacy ``app.domains.packs`` compat-shim was removed in
POST-1 (2026-07-02); the directory was then re-created by BIZ-50 (2026-08-09)
with NEW content (fields/readiness/scenario_preview), splitting one context
across two packages and tripping the ARCH-3 boundary guard on every full run.
Those three modules were folded back here on 2026-08-26 — ``app.domains.packs``
must not come back: the boundary guard treats any new cross-context import as
a failure, with no allowlist entry for packs.

``router`` is exposed lazily (PEP 562): worker/bootstrap import paths
(``services/tasks.py``, ``services/demo_bootstrap.py`` import the ``seeder`` /
``context`` submodules) must not eagerly pull FastAPI/openpyxl via ``.api``.
"""

from __future__ import annotations

from typing import Any

__all__ = ["router"]


def __getattr__(name: str) -> Any:
    if name == "router":
        from app.modules.packs.api import router

        return router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
