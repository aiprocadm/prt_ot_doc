"""Standardized schemas for bulk operation requests and responses.

Use these models as the canonical contract for any endpoint that accepts
multiple IDs and returns per-item outcomes:

    @router.post("/items/bulk-delete", response_model=BulkResponse)
    async def bulk_delete(body: BulkRequest, ...):
        results = []
        for item_id in body.ids:
            try:
                await _delete_one(item_id, ...)
                results.append(BulkItemResult(id=item_id, success=True))
            except Exception as exc:
                results.append(BulkItemResult(id=item_id, success=False, error=str(exc)))
        return BulkResponse.from_results(results)
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from app.schemas.base import BaseSchema


class BulkRequest(BaseSchema):
    """Generic request body for operations targeting multiple resource IDs."""

    ids: list[str] = Field(
        ...,
        min_length=1,
        max_length=500,
        description="List of resource identifiers to operate on.",
    )
    idempotency_key: str | None = Field(
        default=None,
        max_length=128,
        description="Optional client-supplied idempotency key for replay safety.",
    )
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="Operation-specific options (e.g. dry_run, reason, force).",
    )

    @model_validator(mode="after")
    def _deduplicate_ids(self) -> "BulkRequest":
        seen: list[str] = []
        for item_id in self.ids:
            if item_id not in seen:
                seen.append(item_id)
        self.ids = seen
        return self


class BulkItemResult(BaseSchema):
    """Per-item outcome within a bulk operation response."""

    id: str = Field(..., description="Resource identifier this result corresponds to.")
    success: bool = Field(..., description="Whether the operation succeeded for this item.")
    error: str | None = Field(default=None, description="Error message if the operation failed.")
    error_code: str | None = Field(default=None, description="Machine-readable error code.")
    data: dict[str, Any] | None = Field(
        default=None, description="Optional result payload for this item."
    )


class BulkResponse(BaseSchema):
    """Standard envelope returned by bulk operation endpoints."""

    results: list[BulkItemResult] = Field(default_factory=list)
    succeeded: int = Field(default=0, description="Count of items processed successfully.")
    failed: int = Field(default=0, description="Count of items that failed.")
    total: int = Field(default=0, description="Total items submitted.")

    @classmethod
    def from_results(cls, results: list[BulkItemResult]) -> "BulkResponse":
        succeeded = sum(1 for r in results if r.success)
        return cls(
            results=results,
            succeeded=succeeded,
            failed=len(results) - succeeded,
            total=len(results),
        )

    @classmethod
    def all_ok(cls, ids: list[str]) -> "BulkResponse":
        """Convenience factory when all items succeeded without extra data."""
        results = [BulkItemResult(id=item_id, success=True) for item_id in ids]
        return cls.from_results(results)


class BulkStatusUpdateRequest(BulkRequest):
    """Bulk request that also carries a new status value."""

    status: str = Field(..., description="Target status to apply to all matching items.")
    reason: str | None = Field(default=None, description="Optional reason for the status change.")
