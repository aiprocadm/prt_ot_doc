"""Factories for obtaining integration implementations based on feature flags."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings

from .interfaces import (
    BaseAccountingIntegration,
    BaseEDOIntegration,
    BaseEISOTIntegration,
    BaseFRDOIntegration,
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


@lru_cache()
def get_accounting_integration() -> BaseAccountingIntegration:
    settings = get_settings()
    if settings.use_1c_integration:
        return StubAccountingIntegration()
    return DisabledAccountingIntegration()


@lru_cache()
def get_edo_integration() -> BaseEDOIntegration:
    settings = get_settings()
    if settings.use_edo_integration:
        return StubEDOIntegration()
    return DisabledEDOIntegration()


@lru_cache()
def get_frdo_integration() -> BaseFRDOIntegration:
    settings = get_settings()
    if settings.use_frdo_integration:
        return StubFRDOIntegration()
    return DisabledFRDOIntegration()


@lru_cache()
def get_eisot_integration() -> BaseEISOTIntegration:
    settings = get_settings()
    if settings.use_eisot_integration:
        return StubEISOTIntegration()
    return DisabledEISOTIntegration()


def reset_integration_providers() -> None:
    """Clear cached integration instances after settings changes."""

    get_accounting_integration.cache_clear()
    get_edo_integration.cache_clear()
    get_frdo_integration.cache_clear()
    get_eisot_integration.cache_clear()
