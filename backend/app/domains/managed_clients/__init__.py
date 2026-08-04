"""Managed Clients bounded context (BIZ-49 срез-1, разд. 49)."""

from app.domains.managed_clients.lifecycle import (
    ContractStatus,
    ManagedClientMode,
    ManagedClientTransitionError,
    contract_days_left,
    is_contract_expiring,
    validate_contract_transition,
    validate_mode_binding,
)

__all__ = [
    "ContractStatus",
    "ManagedClientMode",
    "ManagedClientTransitionError",
    "contract_days_left",
    "is_contract_expiring",
    "validate_contract_transition",
    "validate_mode_binding",
]
