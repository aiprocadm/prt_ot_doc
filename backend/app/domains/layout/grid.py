from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class GridLayout:
    columns: int

    def apply(self, context: dict[str, Any]) -> dict[str, Any]:
        context = dict(context)
        context["layout_columns"] = self.columns
        return context
