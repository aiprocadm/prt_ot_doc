"""PipelineService package (ARCH-4 slice 9 — god-class decomposed via mixins).

Public surface unchanged: ``from app.services.pipeline import PipelineService,
StampingUnavailableError`` (and ``app.services`` re-exports) resolve as before.
"""

from app.services.pipeline._base import StampingUnavailableError  # noqa: F401
from app.services.pipeline.service import PipelineService  # noqa: F401

__all__ = ["PipelineService", "StampingUnavailableError"]
