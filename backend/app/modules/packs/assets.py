"""Embedded visual assets for default document packs."""

from __future__ import annotations

import base64
from dataclasses import dataclass

__all__ = [
    "DEFAULT_LOGO_BYTES",
    "DEFAULT_STAMP_BYTES",
    "InlineImageDescriptor",
    "build_inline_image_descriptor",
]

# Minimal PNG placeholders (1x1) encoded as base64 to avoid external
# dependencies during tests. Images were generated offline and embedded as
# static constants. Each renders as a coloured banner that fits nicely in a
# header or footer once scaled by the caller.
_LOGO_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)

_STAMP_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgSDsDAAGcATPhsmC5AAAAAElFTkSuQmCC"
)

DEFAULT_LOGO_BYTES: bytes = base64.b64decode(_LOGO_BASE64)
DEFAULT_STAMP_BYTES: bytes = base64.b64decode(_STAMP_BASE64)


@dataclass(slots=True)
class InlineImageDescriptor:
    """Descriptor consumed by :func:`DocxService.render_template` for images."""

    data: bytes
    width_mm: float | None = None
    height_mm: float | None = None
    content_type: str = "image/png"


def build_inline_image_descriptor(
    data: bytes,
    *,
    width_mm: float | None = 45.0,
    height_mm: float | None = None,
) -> dict[str, object]:
    """Create a serialisable descriptor understood by the DOCX renderer."""

    return {
        "_type": "inline_image",
        "data": base64.b64encode(data).decode("ascii"),
        "width_mm": width_mm,
        "height_mm": height_mm,
        "content_type": "image/png",
    }
