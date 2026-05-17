"""Service for per-user saved Smart Calendar views (vNext-CAL-01 / Phase 4.1).

Thin async wrapper over `SavedCalendarView` rows scoped to
`(tenant_id, user_id)`. The service owns name-uniqueness enforcement and
soft-delete semantics; the route layer is responsible only for
authn/authz and HTTP marshaling.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calendar_views import SavedCalendarView

__all__ = ["CalendarViewsService", "SavedCalendarViewNameConflictError"]


class SavedCalendarViewNameConflictError(ValueError):
    """Raised when create/update would violate the (tenant, user, name) unique."""


class CalendarViewsService:
    def __init__(self, *, db: AsyncSession, tenant_id: str, user_id: str) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def _base_filter(self) -> tuple:
        return (
            SavedCalendarView.tenant_id == self.tenant_id,
            SavedCalendarView.user_id == self.user_id,
            SavedCalendarView.deleted_at.is_(None),
        )

    async def list_views(self) -> list[SavedCalendarView]:
        stmt = (
            select(SavedCalendarView)
            .where(and_(*self._base_filter()))
            .order_by(SavedCalendarView.created_at.asc())
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return list(rows)

    async def get(self, view_id: str) -> SavedCalendarView | None:
        stmt = select(SavedCalendarView).where(
            and_(
                *self._base_filter(),
                SavedCalendarView.id == view_id,
            )
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _find_by_name(
        self, name: str, *, exclude_id: str | None = None
    ) -> SavedCalendarView | None:
        criteria = [
            *self._base_filter(),
            SavedCalendarView.name == name,
        ]
        if exclude_id is not None:
            criteria.append(SavedCalendarView.id != exclude_id)
        stmt = select(SavedCalendarView).where(and_(*criteria))
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def create(
        self, *, name: str, payload: dict[str, Any]
    ) -> SavedCalendarView:
        existing = await self._find_by_name(name)
        if existing is not None:
            raise SavedCalendarViewNameConflictError(
                f"Saved view with name {name!r} already exists"
            )
        view = SavedCalendarView(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            name=name,
            payload=payload,
        )
        self.db.add(view)
        await self.db.flush()
        await self.db.refresh(view)
        return view

    async def update(
        self,
        view: SavedCalendarView,
        *,
        name: str,
        payload: dict[str, Any],
    ) -> SavedCalendarView:
        if name != view.name:
            conflict = await self._find_by_name(name, exclude_id=view.id)
            if conflict is not None:
                raise SavedCalendarViewNameConflictError(
                    f"Saved view with name {name!r} already exists"
                )
        view.name = name
        view.payload = payload
        await self.db.flush()
        await self.db.refresh(view)
        return view

    async def delete(self, view: SavedCalendarView) -> None:
        # Hard delete is fine: rows are user-owned and have no FK fan-out.
        await self.db.delete(view)
        await self.db.flush()
