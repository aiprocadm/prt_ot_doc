"""Integration abstractions and factories for external systems."""

from .factory import (
    get_accounting_integration,
    get_edo_integration,
    get_eisot_integration,
    get_frdo_integration,
    reset_integration_providers,
)
from .interfaces import (
    BaseAccountingIntegration,
    BaseEDOIntegration,
    BaseEISOTIntegration,
    BaseFRDOIntegration,
    IntegrationContractError,
    IntegrationDisabledError,
    IntegrationErrorContract,
    IntegrationStatus,
)
from .pilot_adapters import PilotAccountingIntegration, PilotEISOTIntegration, PilotFRDOIntegration
from .stubs import (
    DisabledAccountingIntegration,
    DisabledEDOIntegration,
    DisabledEISOTIntegration,
    DisabledFRDOIntegration,
    StubEDOIntegration,
)

__all__ = [
    "BaseAccountingIntegration",
    "BaseEDOIntegration",
    "BaseEISOTIntegration",
    "BaseFRDOIntegration",
    "IntegrationContractError",
    "IntegrationDisabledError",
    "IntegrationErrorContract",
    "IntegrationStatus",
    "DisabledAccountingIntegration",
    "DisabledEDOIntegration",
    "DisabledEISOTIntegration",
    "DisabledFRDOIntegration",
    "StubEDOIntegration",
    "PilotAccountingIntegration",
    "PilotFRDOIntegration",
    "PilotEISOTIntegration",
    "get_accounting_integration",
    "get_edo_integration",
    "get_eisot_integration",
    "get_frdo_integration",
    "reset_integration_providers",
]
