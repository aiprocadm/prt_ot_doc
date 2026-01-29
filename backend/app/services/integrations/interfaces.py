"""Abstract integration interfaces used across the application."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class IntegrationStatus:
    """Normalized status returned by integrations."""

    external_id: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)
    raw: Any | None = None


class IntegrationDisabledError(RuntimeError):
    """Raised when an integration is disabled via feature flag."""


class BaseIntegration(Protocol):
    """Common contract shared by all integrations."""

    name: str

    async def health_check(self) -> bool:
        """Verify that the integration endpoint is reachable."""


class BaseAccountingIntegration(BaseIntegration, ABC):
    """1C accounting integration."""

    @abstractmethod
    async def export_document(self, payload: dict[str, Any]) -> IntegrationStatus:
        """Send a document to the accounting system and return tracking metadata."""

    @abstractmethod
    async def fetch_document(self, external_id: str) -> dict[str, Any] | None:
        """Fetch a previously exported document by its external identifier."""

    @abstractmethod
    async def sync_status(self, external_id: str) -> IntegrationStatus:
        """Refresh processing status for an exported document."""


class BaseEDOIntegration(BaseIntegration, ABC):
    """Electronic document interchange operator (ЭДО/ЭП)."""

    @abstractmethod
    async def send_document(
        self, *, content: bytes, filename: str, metadata: dict[str, Any] | None = None
    ) -> IntegrationStatus:
        """Submit an outgoing document and return an external tracking id."""

    @abstractmethod
    async def download_document(self, external_id: str) -> bytes:
        """Download a previously exchanged document."""

    @abstractmethod
    async def get_document_status(self, external_id: str) -> IntegrationStatus:
        """Return delivery or signature status for a document."""


class BaseFRDOIntegration(BaseIntegration, ABC):
    """ФРДО integration for educational records."""

    @abstractmethod
    async def submit_record(self, payload: dict[str, Any]) -> IntegrationStatus:
        """Send an education record for registration."""

    @abstractmethod
    async def fetch_record(self, external_id: str) -> dict[str, Any] | None:
        """Retrieve a registered record by identifier."""

    @abstractmethod
    async def get_record_status(self, external_id: str) -> IntegrationStatus:
        """Check whether a submitted record has been processed."""


class BaseEISOTIntegration(BaseIntegration, ABC):
    """ЕИСОТ integration for occupational safety reporting."""

    @abstractmethod
    async def publish_report(self, payload: dict[str, Any]) -> IntegrationStatus:
        """Publish a report to ЕИСОТ."""

    @abstractmethod
    async def get_publication_status(self, external_id: str) -> IntegrationStatus:
        """Retrieve processing status for a published report."""

    @abstractmethod
    async def pull_notifications(self) -> list[IntegrationStatus]:
        """Return pending notifications from the platform."""
