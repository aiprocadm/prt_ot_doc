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
    IntegrationDisabledError,
    IntegrationStatus,
)
from .stubs import (
    DisabledAccountingIntegration,
    DisabledEDOIntegration,
    DisabledEISOTIntegration,
    DisabledFRDOIntegration,
    StubAccountingIntegration,
    StubEDOIntegration,
    StubEISOTIntegration,
    StubFRDOIntegration,
)

__all__ = [
    "BaseAccountingIntegration",
    "BaseEDOIntegration",
    "BaseEISOTIntegration",
    "BaseFRDOIntegration",
    "IntegrationDisabledError",
    "IntegrationStatus",
    "DisabledAccountingIntegration",
    "DisabledEDOIntegration",
    "DisabledEISOTIntegration",
    "DisabledFRDOIntegration",
    "StubAccountingIntegration",
    "StubEDOIntegration",
    "StubEISOTIntegration",
    "StubFRDOIntegration",
    "get_accounting_integration",
    "get_edo_integration",
    "get_eisot_integration",
    "get_frdo_integration",
    "reset_integration_providers",
]
