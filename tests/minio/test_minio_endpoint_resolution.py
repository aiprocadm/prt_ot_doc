import sys
from importlib import util
from pathlib import Path
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[2] / "backend"


def _load_file_storage_module(settings: SimpleNamespace):
    spec = util.spec_from_file_location(
        "tests.minio.file_storage",
        ROOT / "app" / "services" / "file_storage.py",
    )
    assert spec and spec.loader
    module = util.module_from_spec(spec)
    module_name = spec.name

    previous = {
        key: sys.modules.get(key)
        for key in ("app", "app.core", "app.core.config", module_name)
    }
    sys.modules["app"] = ModuleType("app")
    sys.modules["app.core"] = ModuleType("app.core")
    config_module = ModuleType("app.core.config")

    def _get_settings():
        return settings

    config_module.get_settings = _get_settings  # type: ignore[attr-defined]
    sys.modules["app.core.config"] = config_module
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
    finally:
        for key, value in previous.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value

    return module


def test_resolve_endpoint_with_scheme_http() -> None:
    module = _load_file_storage_module(
        SimpleNamespace(
            S3_ENDPOINT="http://minio:9000",
            S3_SECURE=True,
            S3_ACCESS_KEY="key",
            S3_SECRET_KEY="secret",
        )
    )
    endpoint, secure = module._resolve_endpoint("http://minio:9000", secure=True)

    assert endpoint == "minio:9000"
    assert secure is False


def test_resolve_endpoint_with_scheme_https() -> None:
    module = _load_file_storage_module(
        SimpleNamespace(
            S3_ENDPOINT="https://storage.example.com",
            S3_SECURE=False,
            S3_ACCESS_KEY="key",
            S3_SECRET_KEY="secret",
        )
    )
    endpoint, secure = module._resolve_endpoint("https://storage.example.com", secure=False)

    assert endpoint == "storage.example.com"
    assert secure is True


def test_resolve_endpoint_without_scheme_uses_flag() -> None:
    module = _load_file_storage_module(
        SimpleNamespace(
            S3_ENDPOINT="play.min.io",
            S3_SECURE=False,
            S3_ACCESS_KEY="key",
            S3_SECRET_KEY="secret",
        )
    )
    endpoint, secure = module._resolve_endpoint("play.min.io", secure=False)

    assert endpoint == "play.min.io"
    assert secure is False
