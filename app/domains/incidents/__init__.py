"""Incident and inspection domain services."""

from app.domains.incidents.service import (
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
