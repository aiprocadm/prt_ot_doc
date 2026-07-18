"""Context management utilities for Celery task execution."""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Optional

__all__ = ["TaskContext", "get_task_id", "reset_task_id", "set_task_id"]


_TASK_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "celery_task_id", default=None
)


@dataclass(frozen=True, slots=True)
class TaskContext:
    """Container describing the active Celery task context."""

    task_id: Optional[str]


def set_task_id(value: Optional[str]) -> contextvars.Token[Optional[str]]:
    """Store the current Celery task identifier in the execution context."""

    if value:
        normalized = value.strip()
        if normalized:
            return _TASK_ID.set(normalized)
    return _TASK_ID.set(None)


def get_task_id(default: Optional[str] = None) -> Optional[str]:
    """Return the Celery task identifier associated with the current context."""

    task_id = _TASK_ID.get()
    if task_id is None:
        return default
    return task_id


def reset_task_id(token: contextvars.Token[Optional[str]]) -> None:
    """Restore a previously active Celery task identifier."""

    _TASK_ID.reset(token)
