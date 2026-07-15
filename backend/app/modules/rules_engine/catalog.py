"""Каталог событий для конструктора правил: интроспекция typed payload-моделей."""

from __future__ import annotations

import datetime
import types
import typing
from typing import Any

from app.services.events import _PAYLOADS, EventType

# rule.triggered исключён: правила на события самого движка запрещены (guard от каскада).
EXCLUDED_EVENT_TYPES = frozenset({EventType.RULE_TRIGGERED.value})

_SCALARS: list[tuple[type, str]] = [
    (bool, "boolean"),
    (int, "number"),
    (float, "number"),
    (datetime.datetime, "datetime"),
    (datetime.date, "date"),
    (str, "string"),
]


def _kind_for(annotation: Any) -> str:
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        return _kind_for(args[0]) if args else "object"
    if origin in (list, tuple, set):
        return "array"
    if origin is not None:  # Mapping[...] и прочие generic-контейнеры
        return "object"
    for base, kind in _SCALARS:
        if isinstance(annotation, type) and issubclass(annotation, base):
            return kind
    return "object"


def event_catalog() -> list[dict[str, Any]]:
    """[{event_type, fields: [{name, kind}]}] — отсортировано по event_type."""
    items: list[dict[str, Any]] = []
    for event_type, model_cls in _PAYLOADS.items():
        if event_type.value in EXCLUDED_EVENT_TYPES:
            continue
        fields = [
            {"name": name, "kind": _kind_for(field.annotation)}
            for name, field in model_cls.model_fields.items()
        ]
        items.append({"event_type": event_type.value, "fields": fields})
    items.sort(key=lambda i: i["event_type"])
    return items


def known_event_types() -> frozenset[str]:
    return frozenset(i["event_type"] for i in event_catalog())


def known_fields_for(event_type: str) -> frozenset[str] | None:
    for item in event_catalog():
        if item["event_type"] == event_type:
            return frozenset(f["name"] for f in item["fields"])
    return None
