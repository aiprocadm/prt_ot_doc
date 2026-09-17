"""Smart Calendar endpoints (vNext-CAL-01 / Phase 4.1).

`GET /api/v1/calendar/events` returns a unified stream of events from
multiple modules (medicals, PPE, permits, training, inspections,
compliance deadlines, briefings, calendar projections). Each item is
normalized to `CalendarEventItem`; clients render with a single template
regardless of source.

Filters (all optional):
* `from_at` / `to_at` — ISO-8601 datetimes that bound the event anchor.
* `source_types` — repeatable; defaults to all.
* `person_id` — restrict to events tied to one employee.
* `site_id` — restrict to events tied to one site.

Backwards compatibility: when no query params are supplied, the response
contract is `CalendarEventsResponse`. The legacy `{items, total}` shape
returned by the previous implementation is therefore replaced; no
caller in this repo depends on the legacy keys (`source_type`/
`source_id`/`title` are still present per item).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.screen_access import screen_roles
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import Tenant
from app.schemas.calendar import CalendarEventsResponse
from app.services.calendar_aggregator import (
    ALL_SOURCES,
    CalendarAggregatorService,
)
from app.services.calendar_ics import render_calendar_ics

router = APIRouter(prefix="/calendar", tags=["calendar"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


# Роли берутся из единой карты прав экрана (core/screen_access): пункт меню
# виден ровно тем, кого пускает ручка — иначе человек видит раздел и получает
# 403 (docs/audit/ACCESS_MENU_VS_API.md, сторож tests/test_menu_matches_api.py).
_CALENDAR_READ_ROLES = list(screen_roles("calendar.view"))


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


CalendarReadAccess = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id,
            required_roles=_CALENDAR_READ_ROLES,
            action="read calendar",
        )
    ),
]


@router.get(
    "/events",
    response_model=CalendarEventsResponse,
    summary="Smart Calendar aggregator (medicals/PPE/permits/training/inspections/deadlines/briefings)",
)
async def list_events(
    tenant: TenantDep,
    session: SessionDep,
    access: CalendarReadAccess,
    from_at: datetime | None = Query(
        default=None, description="Range start (ISO-8601). Filters by source-specific anchor."
    ),
    to_at: datetime | None = Query(
        default=None, description="Range end (ISO-8601). Filters by source-specific anchor."
    ),
    source_types: list[str] | None = Query(
        default=None,
        description=f"Filter to a subset of {sorted(ALL_SOURCES)!r}",
    ),
    person_id: str | None = Query(default=None),
    site_id: str | None = Query(default=None),
    include_fact: bool = Query(
        default=False,
        description=(
            "When true, populate `expected_at`/`actual_at`/`variance_days` on each "
            "item so the UI can render plan-vs-fact comparison. Default false keeps "
            "the wire payload identical to the pre-vNext-CAL-01 contract."
        ),
    ),
    include_sla: bool = Query(
        default=False,
        description=(
            "When true, populate `days_to_due` and `sla_band` so the UI can show "
            "SLA indicators (e.g. «осталось 5 дн.», «critical», «warning»). Bands "
            "are derived from per-source thresholds; default false keeps the wire "
            "payload identical to the pre-vNext-CAL-01 contract."
        ),
    ),
) -> CalendarEventsResponse:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access

    service = CalendarAggregatorService(tenant_id=str(tenant.id), db=session)
    try:
        return await service.list_events(
            from_at=from_at,
            to_at=to_at,
            source_types=source_types,
            person_id=person_id,
            site_id=site_id,
            include_fact=include_fact,
            include_sla=include_sla,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get(
    "/events.ics",
    response_class=Response,
    summary="Smart Calendar export as RFC 5545 iCalendar (.ics) feed",
    responses={
        200: {
            "content": {"text/calendar": {}},
            "description": "iCalendar (.ics) payload — subscribe from Outlook/Google/Apple Calendar.",
        }
    },
)
async def export_events_ics(
    tenant: TenantDep,
    session: SessionDep,
    access: CalendarReadAccess,
    from_at: datetime | None = Query(default=None),
    to_at: datetime | None = Query(default=None),
    source_types: list[str] | None = Query(
        default=None,
        description=f"Filter to a subset of {sorted(ALL_SOURCES)!r}",
    ),
    person_id: str | None = Query(default=None),
    site_id: str | None = Query(default=None),
    include_fact: bool = Query(
        default=False,
        description=(
            "When true, attach plan-vs-fact metadata (`План: …; Факт: …; "
            "Отклонение: ±N дн.`) to each VEVENT DESCRIPTION."
        ),
    ),
    include_sla: bool = Query(
        default=False,
        description=(
            "When true, attach SLA metadata (`До срока: N дн.` / `Просрочено на N дн.` "
            "/ `Срок сегодня` and `SLA: <band>`) to each VEVENT DESCRIPTION."
        ),
    ),
) -> Response:
    """Export the same aggregator output as an iCalendar feed.

    Reuses `CalendarAggregatorService` so the ICS feed is consistent
    with the JSON endpoint (`GET /events`). All filters are forwarded.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access

    service = CalendarAggregatorService(tenant_id=str(tenant.id), db=session)
    try:
        payload = await service.list_events(
            from_at=from_at,
            to_at=to_at,
            source_types=source_types,
            person_id=person_id,
            site_id=site_id,
            include_fact=include_fact,
            include_sla=include_sla,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    body = render_calendar_ics(payload)
    filename = f"calendar-{payload.generated_at.date().isoformat()}.ics"
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
