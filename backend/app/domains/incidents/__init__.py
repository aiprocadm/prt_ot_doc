"""Deprecated compat-shim — canonical location is :mod:`app.modules.incidents` (ARCH-1)."""

from app.modules.incidents.operations import (  # noqa: F401  (compat re-export)
    add_inspection_result,
    append_log_entry,
    register_incident,
    register_inspection,
    update_incident,
    update_inspection,
)

__all__ = [
    "add_inspection_result",
    "append_log_entry",
    "register_incident",
    "register_inspection",
    "update_incident",
    "update_inspection",
]
