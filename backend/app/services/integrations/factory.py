"""Factories for obtaining integration implementations based on feature flags."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings

from .http_edo import HttpEDOIntegration
from .interfaces import (
    BaseAccountingIntegration,
    BaseEDOIntegration,
    BaseEISOTIntegration,
    BaseFRDOIntegration,
)
from .pilot_adapters import (
    PilotAccountingIntegration,
    PilotEISOTIntegration,
    PilotFRDOIntegration,
)
from .stubs import (
    DisabledAccountingIntegration,
    DisabledEDOIntegration,
    DisabledEISOTIntegration,
    DisabledFRDOIntegration,
)


@lru_cache()
def get_accounting_integration() -> BaseAccountingIntegration:
    settings = get_settings()
    if settings.use_1c_integration:
        return PilotAccountingIntegration()
    return DisabledAccountingIntegration()


@lru_cache()
def get_edo_integration() -> BaseEDOIntegration:
    settings = get_settings()
    if not settings.use_edo_integration:
        return DisabledEDOIntegration()
    base = (settings.edo_integration_base_url or "").strip()
    if base:
        return HttpEDOIntegration(
            base_url=base,
            api_token=settings.edo_integration_api_token,
            timeout_seconds=settings.edo_integration_timeout_seconds,
            outbound_path=settings.edo_integration_outbound_path,
            app_env=settings.app_env,
        )
    # Флаг включён, но base_url не задан: провайдер не сконфигурирован.
    # Честно сообщаем о недоступности (IntegrationDisabledError), не имитируем отправку.
    return DisabledEDOIntegration()


@lru_cache()
def get_frdo_integration() -> BaseFRDOIntegration:
    settings = get_settings()
    if settings.use_frdo_integration:
        return PilotFRDOIntegration()
    return DisabledFRDOIntegration()


@lru_cache()
def get_eisot_integration() -> BaseEISOTIntegration:
    settings = get_settings()
    if settings.use_eisot_integration:
        return PilotEISOTIntegration()
    return DisabledEISOTIntegration()


def reset_integration_providers() -> None:
    """Clear cached integration instances after settings changes."""

    get_accounting_integration.cache_clear()
    get_edo_integration.cache_clear()
    get_frdo_integration.cache_clear()
    get_eisot_integration.cache_clear()
