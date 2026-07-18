from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import EdoMessage, EdoStatusEvent, EdoWebhookInbox


class EdoOperatorAdapter(Protocol):
    async def send_outgoing_message(self, message: EdoMessage) -> dict[str, Any]: ...
    async def get_message_status(self, message: EdoMessage) -> dict[str, Any]: ...
    async def parse_webhook(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def fetch_protocol(self, message: EdoMessage) -> dict[str, Any]: ...


# Мок-оператор удалён (Срез-1 чистка симуляции).
# Реальный оператор ЭДО появится при продуктовой интеграции.


class EdoMessageService:
    """Сервис исходящих ЭДО-сообщений.

    operator=None означает «оператор не сконфигурирован»; методы, не
    использующие оператора напрямую, работают и без него.
    """

    def __init__(
        self, session: AsyncSession, tenant_id: str, operator: EdoOperatorAdapter | None = None
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.operator = operator


class EdoWebhookService:
    def __init__(
        self, session: AsyncSession, tenant_id: str, operator: EdoOperatorAdapter | None = None
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.operator = operator

    async def ingest(
        self,
        *,
        operator_code: str,
        dedupe_key: str,
        headers_json: dict[str, Any],
        payload_json: dict[str, Any],
    ) -> EdoWebhookInbox:
        inbox = EdoWebhookInbox(
            tenant_id=self.tenant_id,
            operator_code=operator_code,
            dedupe_key=dedupe_key,
            headers_json=headers_json,
            payload_json=payload_json,
            status="received",
        )
        self.session.add(inbox)
        await self.session.flush()
        return inbox


class EdoStatusProjectionService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def apply_event(
        self,
        message: EdoMessage,
        event_status: str,
        payload: dict[str, Any],
        dedupe_key: str | None,
    ) -> EdoStatusEvent:
        event = EdoStatusEvent(
            tenant_id=self.tenant_id,
            edo_message_id=message.id,
            status=event_status,
            payload_json=payload,
            dedupe_key=dedupe_key,
            received_at=datetime.now(tz=timezone.utc),
            processed_at=datetime.now(tz=timezone.utc),
        )
        self.session.add(event)
        message.status = event_status
        message.last_status_at = datetime.now(tz=timezone.utc)
        await self.session.flush()
        return event
