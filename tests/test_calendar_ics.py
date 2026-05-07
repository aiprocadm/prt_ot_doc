"""Tests for the Smart Calendar ICS exporter (vNext-CAL-01 / Phase 4.1)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import MedicalExam, RoleEnum
from app.schemas.calendar import (
    CalendarEventItem,
    CalendarEventsResponse,
    CalendarSourceCount,
)
from app.services.calendar_ics import (
    PRODID,
    _escape_text,
    _fold,
    _format_dt,
    _status_value,
    render_calendar_ics,
)
from tests.utils.factories import TestDataFactory

API_PREFIX = "/api/v1"


def _ics_headers(base: dict[str, str]) -> dict[str, str]:
    merged = {**base}
    tid = merged.get("x-tenant") or merged.get("X-Tenant-Id")
    if tid:
        merged.setdefault("X-Tenant-Id", str(tid))
    return merged


# ---------------------------------------------------------------------------
# Pure-function tests
# ---------------------------------------------------------------------------


class TestEscapeText:
    def test_escapes_backslash_first(self) -> None:
        # Backslash must be escaped before commas/semicolons so we don't
        # double-escape the literal `\,` injected for commas.
        assert _escape_text("a\\b") == "a\\\\b"

    def test_escapes_comma_and_semicolon(self) -> None:
        assert _escape_text("a,b;c") == "a\\,b\\;c"

    def test_escapes_newlines_to_literal_n(self) -> None:
        # CRLF, LF and bare CR all collapse to literal \n per §3.3.11.
        assert _escape_text("a\r\nb\nc\rd") == "a\\nb\\nc\\nd"

    def test_passthrough_for_plain_text(self) -> None:
        assert _escape_text("Медосмотр: периодический") == "Медосмотр: периодический"


class TestFormatDt:
    def test_naive_datetime_treated_as_utc(self) -> None:
        value = datetime(2026, 5, 7, 12, 34, 56)
        assert _format_dt(value) == "20260507T123456Z"

    def test_aware_datetime_converted_to_utc(self) -> None:
        plus_three = timezone(timedelta(hours=3))
        value = datetime(2026, 5, 7, 15, 34, 56, tzinfo=plus_three)
        assert _format_dt(value) == "20260507T123456Z"


class TestFold:
    def test_short_line_unchanged(self) -> None:
        line = "SUMMARY:hello"
        assert _fold(line) == line

    def test_long_ascii_line_folded_with_crlf_space(self) -> None:
        # 200 ASCII chars => must split into >=3 parts at 75-octet bounds.
        line = "DESCRIPTION:" + ("a" * 200)
        folded = _fold(line)
        parts = folded.split("\r\n")
        assert len(parts) >= 3
        # First chunk fits 75 octets, continuations start with single space.
        assert len(parts[0].encode("utf-8")) <= 75
        for part in parts[1:]:
            assert part.startswith(" ")
            assert len(part.encode("utf-8")) <= 75
        # Re-join with leading-space stripping recovers the original.
        rejoined = parts[0] + "".join(p[1:] for p in parts[1:])
        assert rejoined == line

    def test_does_not_split_multibyte_utf8(self) -> None:
        # Russian text is 2 bytes/char; force a long SUMMARY that the
        # folder must split without producing invalid UTF-8.
        line = "SUMMARY:" + ("Я" * 80)  # 80 * 2 bytes = 160 octets
        folded = _fold(line)
        # Each chunk must round-trip cleanly through UTF-8.
        for part in folded.split("\r\n"):
            part.encode("utf-8").decode("utf-8")  # raises if invalid
        # Rejoining still yields the original payload.
        parts = folded.split("\r\n")
        rejoined = parts[0] + "".join(p[1:] for p in parts[1:])
        assert rejoined == line


class TestStatusValue:
    def test_maps_known_confirmed_statuses(self) -> None:
        for raw in ("active", "signed", "approved", "completed", "issued", "valid"):
            item = _make_item(status=raw)
            assert _status_value(item) == "CONFIRMED"

    def test_maps_known_tentative_statuses(self) -> None:
        for raw in ("draft", "scheduled", "planned", "upcoming", "review", "expired"):
            item = _make_item(status=raw)
            assert _status_value(item) == "TENTATIVE"

    def test_maps_known_cancelled_statuses(self) -> None:
        for raw in ("cancelled", "canceled", "closed", "revoked", "archived"):
            item = _make_item(status=raw)
            assert _status_value(item) == "CANCELLED"

    def test_unknown_status_defaults_confirmed(self) -> None:
        assert _status_value(_make_item(status="surprise")) == "CONFIRMED"

    def test_empty_status_defaults_confirmed(self) -> None:
        assert _status_value(_make_item(status=None)) == "CONFIRMED"


def _make_item(*, status: str | None) -> CalendarEventItem:
    return CalendarEventItem(
        id="x:1",
        source_type="x",
        source_id="1",
        title="Sample",
        starts_at=datetime(2026, 5, 7, 9, 0, tzinfo=timezone.utc),
        status=status,
    )


# ---------------------------------------------------------------------------
# Renderer tests (compose multiple events into a VCALENDAR)
# ---------------------------------------------------------------------------


class TestRenderCalendarIcs:
    def test_minimal_envelope(self) -> None:
        response = CalendarEventsResponse(
            generated_at=datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
            range_from=None,
            range_to=None,
            total=0,
            overdue_count=0,
            by_source=[],
            items=[],
        )
        text = render_calendar_ics(response)
        # CRLF terminator after every line including final one.
        assert text.startswith("BEGIN:VCALENDAR\r\n")
        assert text.endswith("END:VCALENDAR\r\n")
        assert f"PRODID:{PRODID}" in text
        assert "VERSION:2.0\r\n" in text
        assert "METHOD:PUBLISH\r\n" in text
        assert "BEGIN:VEVENT" not in text  # no events were rendered

    def test_renders_event_with_required_properties(self) -> None:
        item = CalendarEventItem(
            id="medical_exam:abc",
            source_type="medical_exam",
            source_id="abc",
            title="Медосмотр: периодический",
            starts_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            ends_at=None,
            status="active",
            is_overdue=False,
            person_id="person-1",
            site_id=None,
            company_id=None,
        )
        response = CalendarEventsResponse(
            generated_at=datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
            range_from=None,
            range_to=None,
            total=1,
            overdue_count=0,
            by_source=[
                CalendarSourceCount(source_type="medical_exam", count=1, overdue_count=0)
            ],
            items=[item],
        )
        text = render_calendar_ics(response, domain="ot.example")
        assert "BEGIN:VEVENT\r\n" in text
        assert "END:VEVENT\r\n" in text
        assert "UID:medical_exam:abc@ot.example\r\n" in text
        assert "DTSTAMP:20260507T120000Z\r\n" in text
        assert "DTSTART:20260601T090000Z\r\n" in text
        # ru-локалный SUMMARY читаем
        assert "Медосмотр: периодический" in text
        assert "STATUS:CONFIRMED\r\n" in text
        assert "CATEGORIES:medical_exam\r\n" in text
        # No DTEND for point-in-time events.
        assert "DTEND:" not in text

    def test_overdue_event_marked_in_summary_categories_and_status(self) -> None:
        item = CalendarEventItem(
            id="permit:42",
            source_type="permit",
            source_id="42",
            title="Допуск: работа на высоте",
            starts_at=datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc),
            ends_at=None,
            status="expired",
            is_overdue=True,
            person_id="person-x",
        )
        response = CalendarEventsResponse(
            generated_at=datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
            range_from=None,
            range_to=None,
            total=1,
            overdue_count=1,
            by_source=[
                CalendarSourceCount(source_type="permit", count=1, overdue_count=1)
            ],
            items=[item],
        )
        text = render_calendar_ics(response)
        assert "[Просрочено] Допуск: работа на высоте" in text
        # Categories include `overdue` marker.
        assert "CATEGORIES:permit,overdue\r\n" in text
        # `expired` maps to TENTATIVE so the event still renders in clients.
        assert "STATUS:TENTATIVE\r\n" in text

    def test_special_characters_in_title_escaped(self) -> None:
        item = CalendarEventItem(
            id="x:1",
            source_type="x",
            source_id="1",
            title="Title; with, comma\\and\nnewline",
            starts_at=datetime(2026, 5, 7, 9, 0, tzinfo=timezone.utc),
            status="active",
        )
        response = CalendarEventsResponse(
            generated_at=datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
            range_from=None,
            range_to=None,
            total=1,
            overdue_count=0,
            by_source=[CalendarSourceCount(source_type="x", count=1, overdue_count=0)],
            items=[item],
        )
        text = render_calendar_ics(response)
        # Escaped, not raw — the literal newline must NOT appear in
        # SUMMARY because it would break the line model.
        assert "SUMMARY:Title\\; with\\, comma\\\\and\\nnewline" in text

    def test_emits_dtend_when_ends_at_present(self) -> None:
        item = CalendarEventItem(
            id="training_session:9",
            source_type="training_session",
            source_id="9",
            title="Обучение: вводное",
            starts_at=datetime(2026, 5, 7, 9, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 5, 7, 17, 0, tzinfo=timezone.utc),
            status="completed",
        )
        response = CalendarEventsResponse(
            generated_at=datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
            range_from=None,
            range_to=None,
            total=1,
            overdue_count=0,
            by_source=[
                CalendarSourceCount(
                    source_type="training_session", count=1, overdue_count=0
                )
            ],
            items=[item],
        )
        text = render_calendar_ics(response)
        assert "DTSTART:20260507T090000Z\r\n" in text
        assert "DTEND:20260507T170000Z\r\n" in text

    def test_calendar_description_includes_range(self) -> None:
        response = CalendarEventsResponse(
            generated_at=datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
            range_from=datetime(2026, 5, 1, tzinfo=timezone.utc),
            range_to=datetime(2026, 5, 31, tzinfo=timezone.utc),
            total=0,
            overdue_count=0,
            by_source=[],
            items=[],
        )
        text = render_calendar_ics(response)
        assert "X-WR-CALDESC:" in text
        assert "2026-05-01" in text
        assert "2026-05-31" in text


# ---------------------------------------------------------------------------
# Endpoint smoke tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestCalendarIcsEndpoint:
    async def test_returns_text_calendar_for_admin(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            company = await data_factory.create_company(
                tenant=tenant, session=session
            )
            person = await data_factory.create_person(
                tenant=tenant,
                company=company,
                session=session,
                first_name="Ics",
                last_name="Export",
                email="ics-export@example.com",
            )
            today = date.today()
            session.add(
                MedicalExam(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    exam_type="periodic",
                    exam_date=today - timedelta(days=5),
                    valid_until=today + timedelta(days=10),
                )
            )
            await session.commit()

        headers = _ics_headers(await make_auth_headers(RoleEnum.ADMIN))
        response = await async_client.get(
            f"{API_PREFIX}/calendar/events.ics", headers=headers
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        # Media type is text/calendar with utf-8 charset.
        ctype = response.headers["content-type"].lower()
        assert "text/calendar" in ctype
        assert "utf-8" in ctype
        # Filename hint for download.
        cdisp = response.headers.get("content-disposition", "")
        assert "attachment" in cdisp.lower()
        assert ".ics" in cdisp.lower()
        body = response.text
        assert body.startswith("BEGIN:VCALENDAR\r\n")
        assert body.endswith("END:VCALENDAR\r\n")
        # ru-localized SUMMARY survived the round-trip.
        assert "Медосмотр" in body
        assert "BEGIN:VEVENT\r\n" in body

    async def test_empty_feed_for_admin_with_no_data(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            await data_factory.ensure_tenant(session=session)
            await session.commit()

        headers = _ics_headers(await make_auth_headers(RoleEnum.ADMIN))
        response = await async_client.get(
            f"{API_PREFIX}/calendar/events.ics", headers=headers
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        body = response.text
        assert "BEGIN:VEVENT" not in body
        assert "BEGIN:VCALENDAR\r\n" in body
        assert "END:VCALENDAR\r\n" in body

    async def test_rejects_unknown_source_type_with_400(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            await data_factory.ensure_tenant(session=session)
            await session.commit()

        headers = _ics_headers(await make_auth_headers(RoleEnum.ADMIN))
        response = await async_client.get(
            f"{API_PREFIX}/calendar/events.ics?source_types=nope",
            headers=headers,
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    async def test_forbidden_for_unauthorized_role(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            await data_factory.ensure_tenant(session=session)
            await session.commit()

        headers = _ics_headers(await make_auth_headers(RoleEnum.STUDENT))
        response = await async_client.get(
            f"{API_PREFIX}/calendar/events.ics", headers=headers
        )
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }
