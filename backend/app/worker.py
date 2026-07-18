"""Background worker entrypoint."""

from __future__ import annotations

import logging

from .core.config import bootstrap

logger = logging.getLogger("app.worker")


def run() -> None:
    """Run worker boot sequence."""
    settings = bootstrap("worker")
    logger.info(
        "Worker service configuration ready",
        extra={"queues": settings.celery.worker_queues},
    )


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    run()
