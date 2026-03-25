from __future__ import annotations

from datetime import datetime, timezone
from typing import Final

from app.models.models import Inspection, PPEIssue, Tenant, TrainingPlan
from app.models.notifications import (
    Notification,
    NotificationChannel,
    NotificationChannelSettings,
    NotificationPriority,
    NotificationStatus,
    NotificationTemplate,
    NotificationType,
    PlanTask,
    PlanTaskStatus,
)
from app.modules.notifications.schemas import (
    CalendarEventRead,
    ChannelSettingsIn,
    ChannelSettingsOut,
    NotificationPage,
    NotificationRead,
    NotificationTemplateIn,
    NotificationTemplateOut,
)
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

CALENDAR_SOURCES: Final[tuple[str, ...]] = ("task", "training", "ppe", "inspection")


class NotificationApplicationService:
    def __init__(self, session: AsyncSession, tenant: Tenant, user_id: str) -> None:
        self.session = session
        self.tenant = tenant
        self.user_id = user_id

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _parse_enum(enum_cls: type, raw_value: str | None, field_name: str):
        if raw_value is None:
            return None
        try:
            return enum_cls(raw_value)
        except ValueError as exc:
            allowed_values = [item.value for item in enum_cls]
            raise NotificationApplicationService._validation_error(
                field_name=field_name,
                message=f"Unsupported {field_name}: {raw_value}",
                allowed_values=allowed_values,
                provided=raw_value,
                field_error_type="enum",
            ) from exc

    @classmethod
    def _validation_error(
        cls,
        *,
        field_name: str,
        message: str,
        allowed_values: list[str] | None = None,
        provided: str | None = None,
        error_type: str = "validation",
        field_error_type: str = "validation_error",
    ) -> HTTPException:
        details: dict[str, object] = {}
        if allowed_values is not None:
            details["allowed_values"] = allowed_values
        if provided is not None:
            details["provided"] = provided
        payload: dict[str, object] = {
            "message": message,
            "type": error_type,
            "field_errors": [
                {
                    "field": field_name,
                    "message": message,
                    "type": field_error_type,
                }
            ],
        }
        payload.update(details)
        if details:
            payload["details"] = details
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=payload,
        )

    @classmethod
    def _parse_cursor(cls, raw_value: str | None) -> datetime | None:
        if raw_value is None:
            return None
        normalized = raw_value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            return datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise cls._validation_error(
                field_name="cursor",
                message="Cursor must be a valid ISO-8601 datetime",
                provided=raw_value,
                field_error_type="datetime_format",
            ) from exc

    @classmethod
    def _parse_calendar_source(cls, raw_value: str | None) -> str | None:
        if raw_value is None:
            return None
        normalized = raw_value.strip().lower()
        if not normalized:
            return None
        if normalized not in CALENDAR_SOURCES:
            raise cls._validation_error(
                field_name="source",
                message=f"Unsupported source: {raw_value}",
                allowed_values=list(CALENDAR_SOURCES),
                provided=raw_value,
                field_error_type="enum",
            )
        return normalized

    @classmethod
    def _to_notification_read(cls, item: Notification) -> NotificationRead:
        payload = item.payload or {}
        deeplink = payload.get("deeplink")
        return NotificationRead(
            id=item.id,
            channel=item.channel.value,
            type=item.type.value,
            title=item.title,
            body=item.body,
            payload=item.payload,
            priority=item.priority.value,
            status=item.status.value,
            is_read=item.status == NotificationStatus.READ,
            deeplink=str(deeplink) if deeplink else None,
            scheduled_at=item.scheduled_at,
            sent_at=item.sent_at,
        )

    @classmethod
    def _to_template_out(cls, row: NotificationTemplate) -> NotificationTemplateOut:
        return NotificationTemplateOut(
            id=row.id,
            code=row.code,
            channel=row.channel.value,
            type=row.type.value,
            locale=row.locale,
            subject_template=row.subject_template,
            title_template=row.title_template,
            body_template=row.body_template,
            is_active=row.is_active,
            variables_schema=row.variables_schema,
        )

    async def list_notifications(
        self,
        *,
        status_value: str | None,
        priority_value: str | None,
        channel_value: str | None,
        type_value: str | None,
        limit: int,
        cursor: str | None,
    ) -> NotificationPage:
        notification_status = None
        if status_value and status_value != "unread":
            notification_status = self._parse_enum(NotificationStatus, status_value, "status")
        notification_priority = self._parse_enum(NotificationPriority, priority_value, "priority")
        notification_channel = self._parse_enum(NotificationChannel, channel_value, "channel")
        notification_type = self._parse_enum(NotificationType, type_value, "type")
        created_before = self._parse_cursor(cursor)

        stmt = select(Notification).where(
            Notification.tenant_id == self.tenant.id,
            Notification.user_id == self.user_id,
            Notification.deleted_at.is_(None),
        )
        if status_value:
            if status_value == "unread":
                stmt = stmt.where(Notification.status != NotificationStatus.READ)
            else:
                stmt = stmt.where(Notification.status == notification_status)
        if notification_priority is not None:
            stmt = stmt.where(Notification.priority == notification_priority)
        if notification_channel is not None:
            stmt = stmt.where(Notification.channel == notification_channel)
        if notification_type is not None:
            stmt = stmt.where(Notification.type == notification_type)
        if created_before is not None:
            stmt = stmt.where(Notification.created_at < created_before)

        rows = (
            await self.session.execute(stmt.order_by(Notification.created_at.desc()).limit(limit + 1))
        ).scalars().all()
        has_more = len(rows) > limit
        items = rows[:limit]

        unread_count = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(
                    Notification.tenant_id == self.tenant.id,
                    Notification.user_id == self.user_id,
                    Notification.channel == NotificationChannel.INAPP,
                    Notification.deleted_at.is_(None),
                    Notification.status != NotificationStatus.READ,
                )
            )
            or 0
        )
        return NotificationPage(
            items=[self._to_notification_read(item) for item in items],
            next_cursor=items[-1].created_at.isoformat() if has_more and items else None,
            unread_count=unread_count,
        )

    async def mark_read(self, ids: list[str]) -> int:
        stmt = select(Notification).where(
            Notification.tenant_id == self.tenant.id,
            Notification.user_id == self.user_id,
            Notification.channel == NotificationChannel.INAPP,
            Notification.deleted_at.is_(None),
        )
        if ids:
            stmt = stmt.where(Notification.id.in_(ids))
        else:
            stmt = stmt.where(Notification.status != NotificationStatus.READ)
        rows = (await self.session.execute(stmt)).scalars().all()
        updated = 0
        for row in rows:
            if row.status == NotificationStatus.READ:
                continue
            row.status = NotificationStatus.READ
            row.sent_at = row.sent_at or datetime.now(tz=timezone.utc)
            updated += 1
        await self.session.flush()
        await self.session.commit()
        return updated

    async def list_templates(self, *, channel_value: str | None, type_value: str | None) -> list[NotificationTemplateOut]:
        notification_channel = self._parse_enum(NotificationChannel, channel_value, "channel")
        notification_type = self._parse_enum(NotificationType, type_value, "type")
        stmt = select(NotificationTemplate).where(
            NotificationTemplate.tenant_id == self.tenant.id,
            NotificationTemplate.deleted_at.is_(None),
        )
        if notification_channel is not None:
            stmt = stmt.where(NotificationTemplate.channel == notification_channel)
        if notification_type is not None:
            stmt = stmt.where(NotificationTemplate.type == notification_type)
        rows = (
            await self.session.execute(
                stmt.order_by(NotificationTemplate.code.asc(), NotificationTemplate.locale.asc())
            )
        ).scalars().all()
        return [self._to_template_out(row) for row in rows]

    async def upsert_template(self, payload: NotificationTemplateIn) -> NotificationTemplateOut:
        channel = self._parse_enum(NotificationChannel, payload.channel, "channel")
        notification_type = self._parse_enum(NotificationType, payload.type, "type")
        existing = (
            await self.session.execute(
                select(NotificationTemplate).where(
                    NotificationTemplate.tenant_id == self.tenant.id,
                    NotificationTemplate.code == payload.code,
                    NotificationTemplate.channel == channel,
                    NotificationTemplate.locale == payload.locale,
                    NotificationTemplate.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        row = existing or NotificationTemplate(
            tenant_id=self.tenant.id,
            code=payload.code,
            channel=channel,
            locale=payload.locale,
            type=notification_type,
            body_template=payload.body_template,
        )
        if existing is None:
            self.session.add(row)
        row.type = notification_type
        row.subject_template = payload.subject_template
        row.title_template = payload.title_template
        row.body_template = payload.body_template
        row.is_active = payload.is_active
        row.variables_schema = payload.variables_schema
        await self.session.flush()
        await self.session.commit()
        return self._to_template_out(row)

    async def get_settings(self) -> ChannelSettingsOut:
        settings = (
            await self.session.execute(
                select(NotificationChannelSettings).where(
                    NotificationChannelSettings.tenant_id == self.tenant.id,
                    NotificationChannelSettings.user_id == self.user_id,
                    NotificationChannelSettings.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if settings is None:
            settings = NotificationChannelSettings(tenant_id=self.tenant.id, user_id=self.user_id)
            self.session.add(settings)
            await self.session.flush()
        await self.session.commit()
        return ChannelSettingsOut.model_validate(settings, from_attributes=True)

    async def update_settings(self, payload: ChannelSettingsIn) -> ChannelSettingsOut:
        settings = (
            await self.session.execute(
                select(NotificationChannelSettings).where(
                    NotificationChannelSettings.tenant_id == self.tenant.id,
                    NotificationChannelSettings.user_id == self.user_id,
                    NotificationChannelSettings.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if settings is None:
            settings = NotificationChannelSettings(tenant_id=self.tenant.id, user_id=self.user_id)
            self.session.add(settings)
        for key, value in payload.model_dump().items():
            setattr(settings, key, value)
        await self.session.flush()
        await self.session.commit()
        return ChannelSettingsOut.model_validate(settings, from_attributes=True)

    async def list_calendar_events(self, *, status_value: str | None, source: str | None) -> list[CalendarEventRead]:
        events: list[CalendarEventRead] = []
        plan_task_status = self._parse_enum(PlanTaskStatus, status_value, "status") if status_value else None
        calendar_source = self._parse_calendar_source(source)

        task_stmt = select(PlanTask).where(
            PlanTask.tenant_id == self.tenant.id,
            PlanTask.deleted_at.is_(None),
            PlanTask.due_at.is_not(None),
        )
        if plan_task_status is not None:
            task_stmt = task_stmt.where(PlanTask.status == plan_task_status)
        task_rows = (
            await self.session.execute(task_stmt.order_by(PlanTask.due_at.asc()).limit(300))
        ).scalars().all()
        for row in task_rows:
            if calendar_source and calendar_source != "task":
                continue
            if row.due_at is None:
                continue
            events.append(
                CalendarEventRead(
                    id=f"task:{row.id}",
                    source="task",
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    title=row.title,
                    date=self._as_utc(row.due_at),
                    status=row.status.value,
                    deeplink=f"/tasks?entity={row.entity_type}:{row.entity_id}",
                )
            )

        training_rows = (
            await self.session.execute(
                select(TrainingPlan).where(
                    TrainingPlan.tenant_id == self.tenant.id,
                    TrainingPlan.deleted_at.is_(None),
                    TrainingPlan.due_date.is_not(None),
                ).limit(300)
            )
        ).scalars().all()
        for row in training_rows:
            if calendar_source and calendar_source != "training":
                continue
            if row.due_date is None:
                continue
            events.append(
                CalendarEventRead(
                    id=f"training:{row.id}",
                    source="training",
                    entity_type="training",
                    entity_id=row.id,
                    title="Обучение: контрольная дата",
                    date=datetime.combine(row.due_date, datetime.min.time(), tzinfo=timezone.utc),
                    deeplink=f"/training?id={row.id}",
                )
            )

        ppe_rows = (
            await self.session.execute(
                select(PPEIssue).where(
                    PPEIssue.tenant_id == self.tenant.id,
                    PPEIssue.deleted_at.is_(None),
                    PPEIssue.expires_at.is_not(None),
                ).limit(300)
            )
        ).scalars().all()
        for row in ppe_rows:
            if calendar_source and calendar_source != "ppe":
                continue
            if row.expires_at is None:
                continue
            events.append(
                CalendarEventRead(
                    id=f"ppe:{row.id}",
                    source="ppe",
                    entity_type="ppe",
                    entity_id=row.id,
                    title="СИЗ: окончание срока",
                    date=self._as_utc(row.expires_at),
                    deeplink=f"/ppe?issue={row.id}",
                )
            )

        inspection_rows = (
            await self.session.execute(
                select(Inspection).where(
                    Inspection.tenant_id == self.tenant.id,
                    Inspection.deleted_at.is_(None),
                    Inspection.scheduled_at.is_not(None),
                ).limit(300)
            )
        ).scalars().all()
        for row in inspection_rows:
            if calendar_source and calendar_source != "inspection":
                continue
            if row.scheduled_at is None:
                continue
            events.append(
                CalendarEventRead(
                    id=f"inspection:{row.id}",
                    source="inspection",
                    entity_type="inspection",
                    entity_id=row.id,
                    title="Проверка: запланировано",
                    date=datetime.combine(row.scheduled_at, datetime.min.time(), tzinfo=timezone.utc),
                    status=row.status.value if hasattr(row.status, "value") else str(row.status),
                    deeplink=f"/inspections?id={row.id}",
                )
            )
        events.sort(key=lambda item: self._as_utc(item.date))
        return events[:500]
