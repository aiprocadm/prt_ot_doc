"""Org-structure service layer (lightweight tenant-safe facades)."""

from __future__ import annotations

from typing import Any


class PersonService:
    @staticmethod
    def apply_patch(person: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        updated = dict(person)
        updated.update(patch)
        return updated


class WorkplaceService:
    @staticmethod
    def apply_patch(workplace: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        updated = dict(workplace)
        updated.update(patch)
        return updated
