"""Utilities for parsing pagination, sorting and filtering query params."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from pydantic import BaseModel, Field

DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 200


class PageQuery(BaseModel):
    """Normalized pagination parameters."""

    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=DEFAULT_PER_PAGE, ge=1, le=MAX_PER_PAGE)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


@dataclass(slots=True)
class SortItem:
    field: str
    direction: int


class SortQuery(BaseModel):
    raw: str | None = None

    def parse(self) -> list[SortItem]:
        if not self.raw:
            return []
        items: list[SortItem] = []
        for part in self.raw.split(","):
            candidate = part.strip()
            if not candidate:
                continue
            field = candidate
            direction = 1
            if ":" in candidate:
                field, value = candidate.split(":", 1)
                normalized = value.strip()
                direction = -1 if normalized in {"-1", "-", "desc"} else 1
            items.append(SortItem(field=field.strip(), direction=direction))
        return items


@dataclass(slots=True)
class FilterItem:
    field: str
    operator: str
    value: str


class FilterQuery(BaseModel):
    raw: str | None = None

    def parse(self) -> list[FilterItem]:
        if not self.raw:
            return []
        items: list[FilterItem] = []
        for chunk in self.raw.split(";"):
            candidate = chunk.strip()
            if not candidate or ":" not in candidate:
                continue
            field, rest = candidate.split(":", 1)
            if not field.strip():
                continue
            if "," in rest:
                value, op = rest.split(",", 1)
            else:
                value, op = rest, "eq"
            items.append(
                FilterItem(field=field.strip(), operator=op.strip() or "eq", value=value.strip())
            )
        return items


def pagination_meta(page: int, per_page: int, total: int) -> dict[str, Any]:
    pages = 0
    if per_page:
        pages = (total + per_page - 1) // per_page
    return {"page": page, "per_page": per_page, "total": total, "pages": pages}


def apply_pagination(iterable: Iterable[Any], page: int, per_page: int) -> list[Any]:
    start = (page - 1) * per_page
    end = start + per_page
    return list(iterable)[start:end]
