"""Deprecated compat-shim — canonical location is :mod:`app.modules.files.utils` (ARCH-1)."""

from __future__ import annotations

from app.modules.files.utils import (  # noqa: F401  (compat re-export)
    DEFAULT_SNIFF_BYTES,
    MIME_EXTENSION_OVERRIDES,
    build_dated_prefix,
    build_storage_key,
    determine_extension,
    guess_mime_type,
    sha256_digest,
)

__all__ = [
    "DEFAULT_SNIFF_BYTES",
    "MIME_EXTENSION_OVERRIDES",
    "build_dated_prefix",
    "build_storage_key",
    "determine_extension",
    "guess_mime_type",
    "sha256_digest",
]
