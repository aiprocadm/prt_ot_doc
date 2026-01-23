from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

__all__ = [
    "MAX_MAPPING_PAIRS",
    "MAX_STRING_VALUE_LENGTH",
    "OUTPUT_BASENAME_PATTERN",
    "PayloadConstraintError",
    "enforce_mapping_constraints",
    "normalize_output_basename",
]

MAX_MAPPING_PAIRS = 200
MAX_STRING_VALUE_LENGTH = 10_000
OUTPUT_BASENAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class PayloadConstraintError(ValueError):
    """Raised when incoming payload exceeds allowed limits."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def enforce_mapping_constraints(mapping: Mapping[str, Any], *, field: str) -> None:
    """Ensure a mapping does not exceed size or value length limits."""

    if len(mapping) > MAX_MAPPING_PAIRS:
        raise PayloadConstraintError(
            f"{field} cannot contain more than {MAX_MAPPING_PAIRS} entries",
            status_code=413,
        )
    for value in mapping.values():
        if isinstance(value, str) and len(value) > MAX_STRING_VALUE_LENGTH:
            raise PayloadConstraintError(
                f"{field} values must not exceed {MAX_STRING_VALUE_LENGTH} characters",
                status_code=413,
            )


def normalize_output_basename(value: str | None) -> str | None:
    """Strip and validate an optional output basename against the allowed pattern."""

    if value is None:
        return None

    trimmed = value.strip()
    if not trimmed:
        raise PayloadConstraintError("output_basename cannot be blank", status_code=400)

    if not OUTPUT_BASENAME_PATTERN.fullmatch(trimmed):
        raise PayloadConstraintError(
            "output_basename must match pattern [A-Za-z0-9_-]{1,64}",
            status_code=400,
        )

    return trimmed
