"""Progressive compatibility layer for PPE registry ORM models."""

from app.models.models import (
    PPEIssue,
    PPEIssueStatus,
    PPEItem,
    PPEItemCategory,
    PPEStockBatch,
)

__all__ = [
    "PPEItem",
    "PPEItemCategory",
    "PPEIssue",
    "PPEIssueStatus",
    "PPEStockBatch",
]
