"""Stubbed integration implementations used until real clients are added."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .interfaces import (
    BaseAccountingIntegration,
    BaseEDOIntegration,
    BaseEISOTIntegration,
    BaseFRDOIntegration,
    IntegrationDisabledError,
    IntegrationStatus,
)


class DisabledAccountingIntegration(BaseAccountingIntegration):
    name = "disabled-1c"

    async def export_document(self, payload: dict[str, Any]) -> IntegrationStatus:
        raise IntegrationDisabledError("1C integration is disabled")

    async def fetch_document(self, external_id: str) -> dict[str, Any] | None:
        raise IntegrationDisabledError("1C integration is disabled")

    async def sync_status(self, external_id: str) -> IntegrationStatus:
        raise IntegrationDisabledError("1C integration is disabled")

    async def health_check(self) -> bool:
        raise IntegrationDisabledError("1C integration is disabled")


class StubAccountingIntegration(BaseAccountingIntegration):
    name = "stub-1c"

    async def export_document(self, payload: dict[str, Any]) -> IntegrationStatus:
        return IntegrationStatus(
            external_id=f"1c-{int(datetime.now(tz=timezone.utc).timestamp())}",
            status="queued",
            details={"received": True, "payload": payload},
        )

    async def fetch_document(self, external_id: str) -> dict[str, Any] | None:
        return {"external_id": external_id, "content": "stubbed"}

    async def sync_status(self, external_id: str) -> IntegrationStatus:
        return IntegrationStatus(external_id=external_id, status="processed")

    async def health_check(self) -> bool:
        return True


class DisabledEDOIntegration(BaseEDOIntegration):
    name = "disabled-edo"

    async def send_document(
        self, *, content: bytes, filename: str, metadata: dict[str, Any] | None = None
    ) -> IntegrationStatus:
        raise IntegrationDisabledError("EDO integration is disabled")

    async def download_document(self, external_id: str) -> bytes:
        raise IntegrationDisabledError("EDO integration is disabled")

    async def get_document_status(self, external_id: str) -> IntegrationStatus:
        raise IntegrationDisabledError("EDO integration is disabled")

    async def health_check(self) -> bool:
        raise IntegrationDisabledError("EDO integration is disabled")


class StubEDOIntegration(BaseEDOIntegration):
    name = "stub-edo"

    async def send_document(
        self, *, content: bytes, filename: str, metadata: dict[str, Any] | None = None
    ) -> IntegrationStatus:
        return IntegrationStatus(
            external_id=f"edo-{int(datetime.now(tz=timezone.utc).timestamp())}",
            status="sent",
            details={"filename": filename, "size": len(content), "metadata": metadata or {}},
        )

    async def download_document(self, external_id: str) -> bytes:
        return f"stub-document:{external_id}".encode()

    async def get_document_status(self, external_id: str) -> IntegrationStatus:
        return IntegrationStatus(external_id=external_id, status="delivered")

    async def health_check(self) -> bool:
        return True


class DisabledFRDOIntegration(BaseFRDOIntegration):
    name = "disabled-frdo"

    async def submit_record(self, payload: dict[str, Any]) -> IntegrationStatus:
        raise IntegrationDisabledError("FRDO integration is disabled")

    async def fetch_record(self, external_id: str) -> dict[str, Any] | None:
        raise IntegrationDisabledError("FRDO integration is disabled")

    async def get_record_status(self, external_id: str) -> IntegrationStatus:
        raise IntegrationDisabledError("FRDO integration is disabled")

    async def health_check(self) -> bool:
        raise IntegrationDisabledError("FRDO integration is disabled")


class StubFRDOIntegration(BaseFRDOIntegration):
    name = "stub-frdo"

    async def submit_record(self, payload: dict[str, Any]) -> IntegrationStatus:
        return IntegrationStatus(
            external_id=f"frdo-{int(datetime.now(tz=timezone.utc).timestamp())}",
            status="submitted",
            details={"payload": payload},
        )

    async def fetch_record(self, external_id: str) -> dict[str, Any] | None:
        return {"external_id": external_id, "state": "registered"}

    async def get_record_status(self, external_id: str) -> IntegrationStatus:
        return IntegrationStatus(external_id=external_id, status="registered")

    async def health_check(self) -> bool:
        return True


class DisabledEISOTIntegration(BaseEISOTIntegration):
    name = "disabled-eisot"

    async def publish_report(self, payload: dict[str, Any]) -> IntegrationStatus:
        raise IntegrationDisabledError("EISOT integration is disabled")

    async def get_publication_status(self, external_id: str) -> IntegrationStatus:
        raise IntegrationDisabledError("EISOT integration is disabled")

    async def pull_notifications(self) -> list[IntegrationStatus]:
        raise IntegrationDisabledError("EISOT integration is disabled")

    async def health_check(self) -> bool:
        raise IntegrationDisabledError("EISOT integration is disabled")


class StubEISOTIntegration(BaseEISOTIntegration):
    name = "stub-eisot"

    async def publish_report(self, payload: dict[str, Any]) -> IntegrationStatus:
        return IntegrationStatus(
            external_id=f"eisot-{int(datetime.now(tz=timezone.utc).timestamp())}",
            status="queued",
            details={"payload": payload},
        )

    async def get_publication_status(self, external_id: str) -> IntegrationStatus:
        return IntegrationStatus(external_id=external_id, status="accepted")

    async def pull_notifications(self) -> list[IntegrationStatus]:
        now = datetime.now(tz=timezone.utc).isoformat()
        return [
            IntegrationStatus(external_id="notification-1", status="info", details={"timestamp": now}),
        ]

    async def health_check(self) -> bool:
        return True
