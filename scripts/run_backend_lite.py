from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import uvicorn

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
SQLITE_URL = f"sqlite+aiosqlite:///{ROOT_DIR / 'dev.db'}"


def _configure_env() -> None:
    sys.path.insert(0, str(BACKEND_DIR))
    sys.modules.setdefault("crypt", types.SimpleNamespace(crypt=lambda secret, salt: "mocked"))

    os.environ["APP_RUN_MODE"] = "dockerless"
    os.environ["DATABASE_URL"] = SQLITE_URL
    os.environ["STORAGE_BACKEND"] = "local"
    os.environ["S3_BACKEND"] = "local"
    os.environ["STORAGE_ROOT"] = "./.local_storage"
    os.environ["CELERY_EAGER"] = "true"
    os.environ["REDIS_URL"] = "memory://"
    os.environ["REDIS_RESULT_URL"] = "memory://"
    os.environ["RATE_LIMIT_STORAGE_URI"] = "memory://"
    os.environ["ENABLE_METRICS"] = "false"
    os.environ["S3_ENDPOINT"] = "http://localhost"
    os.environ["LIBREOFFICE_BIN"] = sys.executable
    # README demo: tenant demo + admin@example.com — needs tenant row, demo data, and admin user.
    os.environ.setdefault("DEMO_BOOTSTRAP", "1")
    os.environ.setdefault("ADMIN_BOOTSTRAP", "1")
    os.environ.setdefault("ADMIN_TENANT", "demo")
    os.environ.setdefault("ADMIN_PASSWORD", "admin123")


def _prepare_metadata() -> None:
    from app.core.config import bootstrap
    from app.core.runtime_bootstrap import prepare_runtime

    prepare_runtime(bootstrap("api"))


def main() -> None:
    _configure_env()
    _prepare_metadata()

    from app.api.app import create_app
    from app.core.config import bootstrap
    from app.core.logging import configure_logging

    settings = bootstrap("api")
    configure_logging()
    app = create_app(settings=settings)
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()