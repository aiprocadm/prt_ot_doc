"""Packs bounded context (canonical home — ARCH-1).

Logic lives in submodules imported directly (``assets`` / ``context`` /
``definitions`` / ``seeder`` — provisioning and rendering-context helpers;
``operations`` — scenario-profile resolution + ``PackAssembler``; ``service`` /
``schemas`` / ``api`` — pack-run services and the v2 router). The legacy
``app.domains.packs`` package is a deprecated compat-shim re-exporting from here.

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
