from __future__ import annotations

import importlib


def test_backend_module_entrypoint_importable_from_repo_root() -> None:
    module = importlib.import_module("backend.app.main")
    assert getattr(module, "app", None) is not None


def test_top_level_app_compat_package_resolves_backend_modules() -> None:
    module = importlib.import_module("app.api.app")
    assert hasattr(module, "create_app")
