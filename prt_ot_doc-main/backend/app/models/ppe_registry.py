"""Progressive compatibility layer for PPE registry ORM models."""

from app.models.models import PPEIssue, PPEIssueStatus, PPEItem, PPEItemCategory, WarehousePPE

__all__ = ["PPEItem", "PPEItemCategory", "PPEIssue", "PPEIssueStatus", "WarehousePPE"]
