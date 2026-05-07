"""ICS / iCalendar export for the Smart Calendar aggregator (vNext-CAL-01 / Phase 4.1).

Renders a `CalendarEventsResponse` as an RFC 5545 (iCalendar) text
payload. The implementation is pure-Python (no third-party dependency)
because the requirement is narrow: emit a publish-mode VCALENDAR with
one VEVENT per aggregated row. Subscribers (Outlook, Google Calendar,
Apple Calendar) read the result by URL.

Notes
-----
* All date-times are emitted in UTC (`YYYYMMDDTHHMMSSZ`); the aggregator
  already normalizes to UTC via `_coerce_dt` so no extra conversion is
  needed here.
* TEXT-typed properties (SUMMARY, DESCRIPTION, CATEGORIES, X-WR-*) are
  escaped per §3.3.11: `\\`, `,`, `;` and newlines are backslash-escaped.
* Lines are folded at 75 octets per §3.1; folding is byte-aware so it
  never splits a multi-byte UTF-8 sequence (Russian titles like
  «Медосмотр: периодический» fold safely).
* `STATUS` is mapped to the iCalendar tri-state (CONFIRMED / TENTATIVE /
  CANCELLED). Unknown statuses default to CONFIRMED — the same fallback
  Outlook/Google use when STATUS is omitted.
* `UID` is the aggregator composite id plus a domain suffix; this keeps
  it globally unique across tenants and stable across re-exports so
  subscribers correctly update existing entries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from app.schemas.calendar import CalendarEventItem, CalendarEventsResponse

__all__ = [
    "PRODID",
    "render_calendar_ics",
]

PRODID = "-//OT Platform//Smart Calendar//RU"
DEFAULT_CAL_NAME = "ОТ Платформа — Календарь HSE"
DEFAULT_DOMAIN = "ot-platform.local"

_CRLF = "\r\n"
_LINE_LIMIT = 75  # octets, RFC 5545 §3.1

_CONFIRMED_STATUSES = frozenset(
    {"active", "approved", "completed", "issued", "signed", "valid"}
)
_TENTATIVE_STATUSES = frozenset(
    {"draft", "generated", "planned", "review", "scheduled", "upcoming"}
)
_CANCELLED_STATUSES = frozenset(
    {"archived", "cancelled", "canceled", "closed", "revoked"}
)


def _escape_text(value: str) -> str:
    """Escape a TEXT property value per RFC 5545 §3.3.11."""

    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _format_dt(value: datetime) -> str:
    """Emit a UTC date-time per RFC 5545 §3.3.5 (`YYYYMMDDTHHMMSSZ`)."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y%m%dT%H%M%SZ")


def _fold(line: str) -> str:
    """Fold a content line at 75 octets per RFC 5545 §3.1.

    The first chunk fits 75 octets; subsequent continuation chunks fit
    74 octets so the leading SPACE keeps total octets at <=75. Splits
    never occur in the middle of a UTF-8 multi-byte sequence.
    """

    encoded = line.encode("utf-8")
    if len(encoded) <= _LINE_LIMIT:
        return line

    chunks: list[bytes] = []
    start = 0
    while start < len(encoded):
        max_len = _LINE_LIMIT if not chunks else _LINE_LIMIT - 1
        end = min(start + max_len, len(encoded))
        # Walk back while we'd be splitting a multi-byte UTF-8 sequence.
        while end < len(encoded) and (encoded[end] & 0xC0) == 0x80:
            end -= 1
        if end <= start:
            # Pathological input (single multi-byte char wider than 74
            # octets is impossible in valid UTF-8); avoid an infinite
            # loop by emitting whatever fits.
            end = min(start + max_len, len(encoded))
        chunks.append(encoded[start:end])
        start = end

    head = chunks[0].decode("utf-8")
    tail = [" " + chunk.decode("utf-8") for chunk in chunks[1:]]
    return _CRLF.join([head, *tail])


def _status_value(item: CalendarEventItem) -> str:
    """Map a source-specific status into iCalendar STATUS values."""

    raw = (item.status or "").strip().lower()
    if not raw:
        return "CONFIRMED"
    if raw in _CANCELLED_STATUSES:
        return "CANCELLED"
    if raw in _TENTATIVE_STATUSES:
        return "TENTATIVE"
    if raw in _CONFIRMED_STATUSES:
        return "CONFIRMED"
    if raw == "expired":
        # Past-due events stay TENTATIVE so calendar clients still flag
        # them; CANCELLED would hide the row in some clients.
        return "TENTATIVE"
    return "CONFIRMED"


def _build_event(
    item: CalendarEventItem, *, dtstamp: datetime, domain: str
) -> Iterable[str]:
    yield "BEGIN:VEVENT"
    yield _fold(f"UID:{item.id}@{domain}")
    yield f"DTSTAMP:{_format_dt(dtstamp)}"
    yield f"DTSTART:{_format_dt(item.starts_at)}"
    if item.ends_at is not None:
        yield f"DTEND:{_format_dt(item.ends_at)}"

    title = item.title or item.source_type
    if item.is_overdue:
        title = f"[Просрочено] {title}"
    yield _fold(f"SUMMARY:{_escape_text(title)}")

    desc_parts: list[str] = [f"Источник: {item.source_type}"]
    if item.status:
        desc_parts.append(f"Статус: {item.status}")
    if item.is_overdue:
        desc_parts.append("Событие просрочено")
    if item.person_id:
        desc_parts.append(f"person_id: {item.person_id}")
    if item.site_id:
        desc_parts.append(f"site_id: {item.site_id}")
    if item.company_id:
        desc_parts.append(f"company_id: {item.company_id}")
    if item.assigned_user_id:
        desc_parts.append(f"assigned_user_id: {item.assigned_user_id}")
    yield _fold(f"DESCRIPTION:{_escape_text('; '.join(desc_parts))}")

    categories = [_escape_text(item.source_type)]
    if item.is_overdue:
        categories.append("overdue")
    yield _fold(f"CATEGORIES:{','.join(categories)}")
    yield f"STATUS:{_status_value(item)}"
    yield "END:VEVENT"


def render_calendar_ics(
    response: CalendarEventsResponse,
    *,
    domain: str = DEFAULT_DOMAIN,
    calendar_name: str = DEFAULT_CAL_NAME,
) -> str:
    """Render a `CalendarEventsResponse` as RFC 5545 iCalendar text."""

    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        _fold(f"X-WR-CALNAME:{_escape_text(calendar_name)}"),
    ]
    if response.range_from is not None or response.range_to is not None:
        from_label = (
            response.range_from.date().isoformat() if response.range_from else "—"
        )
        to_label = (
            response.range_to.date().isoformat() if response.range_to else "—"
        )
        lines.append(
            _fold(
                f"X-WR-CALDESC:{_escape_text(f'Период: {from_label} … {to_label}')}"
            )
        )

    for item in response.items:
        lines.extend(_build_event(item, dtstamp=response.generated_at, domain=domain))

    lines.append("END:VCALENDAR")
    return _CRLF.join(lines) + _CRLF
