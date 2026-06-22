"""Pilot-grade adapters for integrations that are not production-ready yet."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .interfaces import (
    BaseAccountingIntegration,
    BaseEISOTIntegration,
    BaseFRDOIntegration,
    IntegrationContractError,
    IntegrationErrorContract,
    IntegrationStatus,
)


def _pilot_details(
    *,
    provider: str,
    operation: str,
    feature_flag: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "adapter_type": "pilot",
        "maturity": "pilot",
        "provider": provider,
        "operation": operation,
        "feature_flag": feature_flag,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    if extra:
        details.update(extra)
    return details


def _require_payload_value(
    *,
    provider: str,
    field_name: str,
    payload: dict[str, Any],
) -> None:
    value = payload.get(field_name)
    if isinstance(value, str) and value.strip():
        return
    raise IntegrationContractError(
        IntegrationErrorContract(
            provider=provider,
            code="validation_error",
            message=f"Missing required field: {field_name}",
            retryable=False,
            http_status=400,
            details={"field": field_name},
        )
    )


class PilotAccountingIntegration(BaseAccountingIntegration):
    name = "pilot-1c"
    feature_flag = "USE_1C_INTEGRATION"

    async def export_document(self, payload: dict[str, Any]) -> IntegrationStatus:
        _require_payload_value(provider=self.name, field_name="document_number", payload=payload)
        return IntegrationStatus(
            external_id=f"pilot-1c-{int(datetime.now(tz=timezone.utc).timestamp())}",
            status="queued",
            details=_pilot_details(
                provider=self.name,
                operation="export_document",
                feature_flag=self.feature_flag,
                extra={"contract_only": True},
            ),
        )

    async def fetch_document(self, external_id: str) -> dict[str, Any] | None:
        return {
            "external_id": external_id,
            "state": "pilot_stubbed",
            "adapter_type": "pilot",
        }

    async def sync_status(self, external_id: str) -> IntegrationStatus:
        return IntegrationStatus(
            external_id=external_id,
            status="pilot_processed",
            details=_pilot_details(
                provider=self.name,
                operation="sync_status",
                feature_flag=self.feature_flag,
            ),
        )

    async def health_check(self) -> bool:
        return True


class PilotFRDOIntegration(BaseFRDOIntegration):
    name = "pilot-frdo"
    feature_flag = "USE_FRDO_INTEGRATION"

    async def submit_record(self, payload: dict[str, Any]) -> IntegrationStatus:
        _require_payload_value(provider=self.name, field_name="person_snils", payload=payload)
        return IntegrationStatus(
            external_id=f"pilot-frdo-{int(datetime.now(tz=timezone.utc).timestamp())}",
            status="submitted",
            details=_pilot_details(
                provider=self.name,
                operation="submit_record",
                feature_flag=self.feature_flag,
                extra={"contract_only": True},
            ),
        )

    async def fetch_record(self, external_id: str) -> dict[str, Any] | None:
        return {"external_id": external_id, "state": "accepted_for_review", "adapter_type": "pilot"}

    async def get_record_status(self, external_id: str) -> IntegrationStatus:
        return IntegrationStatus(
            external_id=external_id,
            status="in_review",
            details=_pilot_details(
                provider=self.name,
                operation="get_record_status",
                feature_flag=self.feature_flag,
            ),
        )

    async def health_check(self) -> bool:
        return True


class PilotEISOTIntegration(BaseEISOTIntegration):
    name = "pilot-eisot"
    feature_flag = "USE_EISOT_INTEGRATION"

    async def publish_report(self, payload: dict[str, Any]) -> IntegrationStatus:
        _require_payload_value(provider=self.name, field_name="report_period", payload=payload)
        return IntegrationStatus(
            external_id=f"pilot-eisot-{int(datetime.now(tz=timezone.utc).timestamp())}",
            status="queued",
            details=_pilot_details(
                provider=self.name,
                operation="publish_report",
                feature_flag=self.feature_flag,
                extra={"contract_only": True},
            ),
        )

    async def get_publication_status(self, external_id: str) -> IntegrationStatus:
        return IntegrationStatus(
            external_id=external_id,
            status="queued",
            details=_pilot_details(
                provider=self.name,
                operation="get_publication_status",
                feature_flag=self.feature_flag,
            ),
        )

    async def pull_notifications(self) -> list[IntegrationStatus]:
        return [
            IntegrationStatus(
                external_id="pilot-eisot-notification-1",
                status="info",
                details=_pilot_details(
                    provider=self.name,
                    operation="pull_notifications",
                    feature_flag=self.feature_flag,
                ),
            )
        ]

    async def health_check(self) -> bool:
        return True
