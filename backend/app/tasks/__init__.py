"""Пакет задач Celery. Совместимость: ``from app.tasks import …``, имена ``app.tasks.*``.

Реализация в :mod:`app.tasks._core`; дальнейшее дробление — без смены публичных импортов.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any

_core: ModuleType = import_module("app.tasks._core")


def __getattr__(name: str) -> Any:
    return getattr(_core, name)


def __dir__() -> list[str]:
    return sorted(n for n in dir(_core) if not n.startswith("__"))


__all__ = [n for n in dir(_core) if not n.startswith("__")]
