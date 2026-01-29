"""API service entrypoint."""

from __future__ import annotations

from app.api.app import create_app
from app.core.config import bootstrap
from app.core.logging import configure_logging

settings = bootstrap("api")
configure_logging()
app = create_app(settings=settings)


def run() -> None:
    """Convenience entry point for running the API with Uvicorn."""

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=getattr(settings, "debug", False),
    )


if __name__ == "__main__":  # pragma: no cover - CLI helper
    run()
