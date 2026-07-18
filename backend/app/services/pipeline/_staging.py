"""PipelineService stage-tracking helpers (ARCH-4 slice 9 split)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.models import PipelineRun


class StagingMixin:
    """Output stage bookkeeping (init/completed/record)."""

    @staticmethod
    def _init_outputs(run: PipelineRun) -> dict[str, Any]:
        outputs = dict(run.outputs or {})
        outputs.setdefault("stages", {})
        return outputs

    @staticmethod
    def _stage_completed(outputs: dict[str, Any], stage: str) -> bool:
        stages = outputs.get("stages") or {}
        entry = stages.get(stage) or {}
        return entry.get("status") == "success"

    @staticmethod
    def _record_stage(
        outputs: dict[str, Any],
        *,
        stage: str,
        status: str,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        stages = dict(outputs.get("stages") or {})
        entry = dict(stages.get(stage) or {})
        if started_at is not None:
            entry["started_at"] = started_at.isoformat()
        if finished_at is not None:
            entry["finished_at"] = finished_at.isoformat()
        entry["status"] = status
        if details:
            entry.setdefault("details", {})
            entry["details"].update(details)
        stages[stage] = entry
        # Return a NEW top-level dict so every ``run.outputs = self._record_stage(...)``
        # reassignment has a fresh object identity. ``PipelineRun.outputs`` is a plain
        # ``JSON`` column (no ``MutableDict``), so SQLAlchemy only flags the attribute
        # dirty when the assigned object differs by identity. Mutating-and-returning the
        # same dict (the previous behaviour) left the column unchanged after the first
        # flush, silently dropping the stage timeline on ``session.refresh``.
        new_outputs = dict(outputs)
        new_outputs["stages"] = stages
        return new_outputs
