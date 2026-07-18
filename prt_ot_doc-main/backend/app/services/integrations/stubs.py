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


def _stub_details(*, provider: str, operation: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider_mode": "non_production",
        "adapter_type": "stub",
        "provider": provider,
        "operation": operation,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    if extra:
        payload.update(extra)
    return payload


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
            details=_stub_details(
                provider=self.name,
                operation="export_document",
                extra={"received": True, "payload": payload},
            ),
        )

    async def fetch_document(self, external_id: str) -> dict[str, Any] | None:
        return {"external_id": external_id, "content": "stubbed"}

    async def sync_status(self, external_id: str) -> IntegrationStatus:
        return IntegrationStatus(
            external_id=external_id,
            status="processed",
            details=_stub_details(provider=self.name, operation="sync_status"),
        )

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
            details=_stub_details(
                provider=self.name,
                operation="send_document",
                extra={"filename": filename, "size": len(content), "metadata": metadata or {}},
            ),
        )

    async def download_document(self, external_id: str) -> bytes:
        return f"stub-document:{external_id}".encode()

    async def get_document_status(self, external_id: str) -> IntegrationStatus:
        return IntegrationStatus(
            external_id=external_id,
            status="delivered",
            details=_stub_details(provider=self.name, operation="get_document_status"),
        )

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
            details=_stub_details(provider=self.name, operation="submit_record", extra={"payload": payload}),
        )

    async def fetch_record(self, external_id: str) -> dict[str, Any] | None:
        return {"external_id": external_id, "state": "registered"}

    async def get_record_status(self, external_id: str) -> IntegrationStatus:
        return IntegrationStatus(
            external_id=external_id,
            status="registered",
            details=_stub_details(provider=self.name, operation="get_record_status"),
        )

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
            details=_stub_details(provider=self.name, operation="publish_report", extra={"payload": payload}),
        )

    async def get_publication_status(self, external_id: str) -> IntegrationStatus:
        return IntegrationStatus(
            external_id=external_id,
            status="accepted",
            details=_stub_details(provider=self.name, operation="get_publication_status"),
        )

    async def pull_notifications(self) -> list[IntegrationStatus]:
        now = datetime.now(tz=timezone.utc).isoformat()
        return [
            IntegrationStatus(
                external_id="notification-1",
                status="info",
                details=_stub_details(provider=self.name, operation="pull_notifications", extra={"timestamp": now}),
            ),
        ]

    async def health_check(self) -> bool:
        return True
