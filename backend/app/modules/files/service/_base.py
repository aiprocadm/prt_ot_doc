"""FileService shared foundation — imports, constants, `s3`, file helpers (ARCH-4 slice 10)."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.core.config import get_settings

MAX_INDEX_BYTES = 25 * 1024 * 1024
MAX_INDEX_CHARS = 500_000

logger = logging.getLogger(__name__)

_PII_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE), "[masked_email]"),
    (
        re.compile(r"(?:\+7|8)?[\s\-()]?\d{3}[\s\-()]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"),
        "[masked_phone]",
    ),
    (re.compile(r"\b\d{4}\s?\d{6}\b"), "[masked_passport]"),
)


def resolve_presign_ttl(requested_ttl: int | None = None) -> int:
    settings = get_settings()
    policy_ttl = int(getattr(settings, "presign_download_ttl_seconds", 600))
    policy_ttl = max(60, min(policy_ttl, 900))
    if requested_ttl is None:
        return policy_ttl
    return max(60, min(int(requested_ttl), policy_ttl))


def _sha256_bytes(payload: bytes) -> str:
    h = hashlib.sha256()
    h.update(payload)
    return h.hexdigest()


def compute_sha256_stream(chunks: list[bytes]) -> str:
    h = hashlib.sha256()
    for chunk in chunks:
        h.update(chunk)
    return h.hexdigest()


def _safe_filename(filename: str | None, fallback: str = "artifact.bin") -> str:
    candidate = (filename or fallback).strip().replace("/", "_").replace("..", "_")
    return candidate or fallback


_DANGEROUS_TRAILING_EXTENSIONS = {
    "bat",
    "cmd",
    "com",
    "exe",
    "hta",
    "jar",
    "js",
    "jse",
    "lnk",
    "msi",
    "ps1",
    "scr",
    "vbe",
    "vbs",
}


def _reject_dangerous_double_extension(filename: str, *, allowed_extensions: set[str]) -> None:
    suffixes = [part.lower() for part in Path(filename).suffixes if part]
    if len(suffixes) < 2:
        return
    normalized = [part.lstrip(".") for part in suffixes]
    if normalized[-1] not in _DANGEROUS_TRAILING_EXTENSIONS:
        return
    if normalized[-2] in allowed_extensions:
        raise HTTPException(status_code=400, detail="dangerous_double_extension")


def _mask_pii(text: str) -> str:
    masked = text
    for pattern, replacement in _PII_PATTERNS:
        masked = pattern.sub(replacement, masked)
    return masked


def _normalize_name_part(value: Any, fallback: str) -> str:
    raw = str(value).strip() if value is not None else ""
    if not raw:
        return fallback
    normalized = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in raw)
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized.lower() or fallback


def build_artifact_name(payload: dict[str, Any] | None, ext: str) -> str:
    data = payload or {}
    org = _normalize_name_part(data.get("org"), "org")
    unit = _normalize_name_part(data.get("unit"), "unit")
    project = _normalize_name_part(data.get("project"), "project")
    client = _normalize_name_part(data.get("client"), "client")
    doc = _normalize_name_part(data.get("doc"), "doc")
    topic = _normalize_name_part(data.get("topic"), "topic")
    version = int(data.get("version") or 1)
    if data.get("date"):
        date_str = str(data["date"]).replace("-", "")[:8]
    else:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    parts = [org, unit, project, client, doc, topic, f"v{version:02d}", date_str]
    flags = data.get("flags") or []
    if isinstance(flags, str):
        flags = [flags]
    if isinstance(flags, list):
        for flag in flags:
            normalized_flag = _normalize_name_part(flag, "")
            if normalized_flag:
                parts.append(normalized_flag)
    base = "_".join(parts)
    normalized_ext = ext if ext.startswith(".") else f".{ext}"
    return f"{base}{normalized_ext}"
