"""Runtime locale and timezone configuration helpers."""

from __future__ import annotations

import locale
import logging
import os
import time
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RuntimeLocale:
    """Container describing configured locale and timezone."""

    locale_name: str
    timezone: ZoneInfo


_DEFAULT_TIMEZONE = ZoneInfo("UTC")
_runtime_timezone: ZoneInfo = _DEFAULT_TIMEZONE


def _iter_locale_candidates(locale_name: str) -> list[str]:
    """Return locale names to try for the provided configuration value."""

    normalized = locale_name.strip()
    if not normalized:
        return []

    def _bcp47_to_posix(name: str) -> str:
        name = name.strip()
        if not name:
            return name
        parts = name.split("-")
        if len(parts) == 1:
            return parts[0]
        language = parts[0].lower()
        transformed: list[str] = []
        for part in parts[1:]:
            if len(part) == 4 and part.isalpha():
                transformed.append(part.title())
            else:
                transformed.append(part.upper())
        return "_".join([language, *transformed])

    base_candidates: list[str] = []
    seen: set[str] = set()

    def add_base(value: str) -> None:
        candidate = value.strip()
        if not candidate:
            return
        candidate = candidate.replace("-", "_")
        if candidate not in seen and candidate.upper() not in {"C", "C.UTF-8"}:
            seen.add(candidate)
            base_candidates.append(candidate)

    add_base(_bcp47_to_posix(normalized))
    add_base(normalized)

    if "-" in normalized:
        add_base(normalized.replace("-", "_"))

    final_candidates: list[str] = []
    seen_final: set[str] = set()

    def add_final(value: str) -> None:
        candidate = value.strip()
        if not candidate:
            return
        upper = candidate.upper()
        if upper in {"C", "C.UTF-8"}:
            return
        if candidate not in seen_final:
            seen_final.add(candidate)
            final_candidates.append(candidate)

    for base in base_candidates:
        add_final(base)

    for base in base_candidates:
        if "." not in base:
            add_final(f"{base}.UTF-8")

    for base in base_candidates:
        normalized_variant = locale.normalize(base).strip()
        add_final(normalized_variant)

    return final_candidates


def _apply_locale(locale_name: str) -> str:
    normalized = locale_name.strip()
    if not normalized:
        return locale.setlocale(locale.LC_ALL, "C")

    if normalized.upper() in {"C", "C.UTF-8"}:
        return locale.setlocale(locale.LC_ALL, "C")

    candidates = list(_iter_locale_candidates(locale_name))

    for candidate in candidates:
        try:
            return locale.setlocale(locale.LC_ALL, candidate)
        except locale.Error:
            continue

    logger.warning("Locale '%s' is not available on this system", normalized)
    return locale.setlocale(locale.LC_ALL, "C")


def _apply_timezone(timezone_name: str) -> ZoneInfo:
    candidate = timezone_name.strip() or "UTC"
    try:
        tz = ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        logger.warning("Timezone '%s' is not recognized; falling back to UTC", candidate)
        tz = _DEFAULT_TIMEZONE

    os.environ["TZ"] = tz.key
    if hasattr(time, "tzset"):
        time.tzset()
    return tz


def configure_runtime_locale(*, locale_name: str, timezone_name: str) -> RuntimeLocale:
    """Apply locale and timezone configuration for the running process."""

    configured_locale = _apply_locale(locale_name)
    configured_tz = _apply_timezone(timezone_name)
    _set_runtime_timezone(configured_tz)
    return RuntimeLocale(locale_name=configured_locale, timezone=configured_tz)


def _set_runtime_timezone(timezone: ZoneInfo) -> None:
    global _runtime_timezone
    _runtime_timezone = timezone


def get_runtime_timezone() -> ZoneInfo:
    """Return the timezone configured for the running process."""

    return _runtime_timezone


__all__ = ["RuntimeLocale", "configure_runtime_locale", "get_runtime_timezone"]
