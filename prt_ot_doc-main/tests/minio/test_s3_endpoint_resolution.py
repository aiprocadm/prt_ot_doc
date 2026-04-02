import sys
from importlib import util
from pathlib import Path
from types import ModuleType, SimpleNamespace

APP_ROOT = Path(__file__).resolve().parents[2] / "backend" / "app"


def _load_s3_module(settings: SimpleNamespace):
    spec = util.spec_from_file_location(
        "tests.minio.backend_s3",
        APP_ROOT / "domains" / "files" / "s3.py",
    )
    assert spec and spec.loader
    module = util.module_from_spec(spec)

    previous = {key: sys.modules.get(key) for key in ("app", "app.core", "app.core.config")}
    app_module = ModuleType("app")
    core_module = ModuleType("app.core")
    config_module = ModuleType("app.core.config")

    def _get_settings():
        return settings

    config_module.get_settings = _get_settings  # type: ignore[attr-defined]

    sys.modules["app"] = app_module
    sys.modules["app.core"] = core_module
    sys.modules["app.core.config"] = config_module

    try:
        spec.loader.exec_module(module)
    finally:
        for key, value in previous.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value

    return module


def test_resolve_endpoint_with_scheme() -> None:
    module = _load_s3_module(
        SimpleNamespace(
            s3_secure=True,
        )
    )
    endpoint, secure = module._resolve_endpoint("http://minio:9000", secure=True)

    assert endpoint == "http://minio:9000"
    assert secure is False


def test_resolve_endpoint_without_scheme_uses_flag() -> None:
    module = _load_s3_module(
        SimpleNamespace(
            s3_secure=False,
        )
    )
    endpoint, secure = module._resolve_endpoint("minio:9000", secure=False)

    assert endpoint == "minio:9000"
    assert secure is False
