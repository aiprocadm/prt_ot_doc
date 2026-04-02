from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import EdoMessage, EdoStatusEvent, EdoWebhookInbox


class EdoOperatorAdapter(Protocol):
    async def send_outgoing_message(self, message: EdoMessage) -> dict[str, Any]: ...
    async def get_message_status(self, message: EdoMessage) -> dict[str, Any]: ...
    async def parse_webhook(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def fetch_protocol(self, message: EdoMessage) -> dict[str, Any]: ...


@dataclass
class MockEdoOperator:
    async def send_outgoing_message(self, message: EdoMessage) -> dict[str, Any]:
        return {"external_message_id": f"edo-{message.id}", "status": "sent"}

    async def get_message_status(self, message: EdoMessage) -> dict[str, Any]:
        progression = ["queued", "sent", "delivered", "viewed", "signed", "completed"]
        try:
            idx = progression.index(message.status)
            status = progression[min(idx + 1, len(progression) - 1)]
        except ValueError:
            status = "sent"
        return {"status": status}

    async def parse_webhook(self, payload: dict[str, Any]) -> dict[str, Any]:
        return payload

    async def fetch_protocol(self, message: EdoMessage) -> dict[str, Any]:
        return {"protocol": {"message_id": message.id, "status": message.status}}


class EdoMessageService:
    def __init__(self, session: AsyncSession, tenant_id: str, operator: EdoOperatorAdapter | None = None) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.operator = operator or MockEdoOperator()


class EdoWebhookService:
    def __init__(self, session: AsyncSession, tenant_id: str, operator: EdoOperatorAdapter | None = None) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.operator = operator or MockEdoOperator()

    async def ingest(self, *, operator_code: str, dedupe_key: str, headers_json: dict[str, Any], payload_json: dict[str, Any]) -> EdoWebhookInbox:
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

    async def apply_event(self, message: EdoMessage, event_status: str, payload: dict[str, Any], dedupe_key: str | None) -> EdoStatusEvent:
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
