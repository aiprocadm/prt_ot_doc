"""Utilities for file metadata normalisation and hashing."""

from __future__ import annotations

import datetime as dt
import hashlib
import mimetypes
import uuid
from pathlib import Path
from typing import Iterable, Mapping

from app.core.tenant import tenant_prefix_path


def _slugify_segment(value: str) -> str:
    """Return a filesystem-safe slug for path segments."""

    normalized = value.strip().lower().replace(" ", "-")
    allowed = []
    for char in normalized:
        if char.isalnum() or char in {"-", "_"}:
            allowed.append(char)
        else:
            allowed.append("-")
    result = "".join(allowed).strip("-_")
    return result or "unknown"

try:  # pragma: no cover - optional dependency during docs builds
    import magic  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - graceful degradation if libmagic is unavailable
    magic = None  # type: ignore[assignment]

__all__ = [
    "DEFAULT_SNIFF_BYTES",
    "MIME_EXTENSION_OVERRIDES",
    "build_dated_prefix",
    "build_storage_key",
    "determine_extension",
    "guess_mime_type",
    "sha256_digest",
]

DEFAULT_SNIFF_BYTES = 4096
MIME_EXTENSION_OVERRIDES: Mapping[str, str] = {
    "image/jpeg": "jpg",
    "text/plain": "txt",
}


def sha256_digest(chunks: Iterable[bytes]) -> str:
    """Compute SHA-256 hex digest for an iterable of byte chunks."""

    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()


def guess_mime_type(
    *,
    filename: str | None,
    provided: str | None,
    sample: bytes | None,
) -> str:
    """Infer MIME type from content, provided header, and filename."""

    candidates: list[str] = []

    if provided:
        candidates.append(provided.lower())

    if sample:
        try:
            if magic is not None:  # pragma: no branch - tiny function
                detected = magic.from_buffer(sample, mime=True)
                if detected:
                    candidates.append(str(detected))
        except Exception:  # pragma: no cover - libmagic edge cases
            pass

    if filename:
        guessed, _ = mimetypes.guess_type(filename)
        if guessed:
            candidates.append(guessed.lower())

    for candidate in candidates:
        normalized = candidate.strip().lower()
        if normalized:
            return normalized

    return "application/octet-stream"


def determine_extension(filename: str | None, mime: str) -> str:
    """Normalise file extension using filename, MIME overrides and guesses."""

    if filename:
        suffix = Path(filename).suffix.lower()
        if suffix:
            candidate = suffix.lstrip(".")
            if candidate.isascii() and candidate.replace(".", "").isalnum():
                return candidate

    override = MIME_EXTENSION_OVERRIDES.get(mime)
    if override:
        return override

    guessed = mimetypes.guess_extension(mime)
    if guessed:
        return guessed.lstrip(".")

    return "bin"


def build_dated_prefix(
    tenant_slug: str,
    *,
    now: dt.datetime | None = None,
) -> str:
    """Return a tenant-specific prefix grouped by calendar month."""

    current = now or dt.datetime.now(dt.timezone.utc)
    base = tenant_prefix_path(tenant_slug)
    if not base.startswith("tenants/"):
        base = f"tenants/{base}"
    return f"{base}/{current.year:04d}/{current.month:02d}"


def build_storage_key(
    *,
    tenant_slug: str,
    sha256_hex: str,
    extension: str,
    company_slug: str | None = None,
    kind: str | None = None,
    pack_code: str | None = None,
    scenario: str | None = None,
    now: dt.datetime | None = None,
) -> str:
    """Construct an object storage key following the tenant namespace convention."""

    current = now or dt.datetime.now(dt.timezone.utc)
    base = tenant_prefix_path(tenant_slug)
    if not base.startswith("tenants/"):
        base = f"tenants/{base}"

    segments: list[str] = [base]
    if company_slug:
        segments.extend(["companies", _slugify_segment(company_slug)])
    if kind:
        segments.extend(["kind", _slugify_segment(kind)])
    if pack_code:
        segments.extend(["packs", _slugify_segment(pack_code)])
    if scenario:
        segments.extend(["scenario", _slugify_segment(scenario)])

    segments.extend([f"{current.year:04d}", f"{current.month:02d}"])

    unique_suffix = uuid.uuid4().hex
    filename = f"{sha256_hex}-{unique_suffix}.{extension}"
    return "/".join([*segments, filename])
