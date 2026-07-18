from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderDescriptor:
    code: str
    mode: str
    production_ready: bool
    warning: str | None = None


_NON_PRODUCTION_HINTS = ("stub", "mock", "fake", "demo", "sandbox", "test", "disabled", "fallback")


def describe_provider(code: str | None) -> ProviderDescriptor:
    normalized = (code or "").strip() or "unspecified"
    lowered = normalized.lower()
    if any(hint in lowered for hint in _NON_PRODUCTION_HINTS):
        return ProviderDescriptor(
            code=normalized,
            mode="non_production",
            production_ready=False,
            warning=(
                f"Provider '{normalized}' is configured in non-production mode. "
                "Use certified adapters only after production integration is implemented."
            ),
        )
    return ProviderDescriptor(code=normalized, mode="production_candidate", production_ready=True)


def provider_response_meta(code: str | None) -> dict[str, str | bool]:
    descriptor = describe_provider(code)
    payload: dict[str, str | bool] = {
        "provider_code": descriptor.code,
        "provider_mode": descriptor.mode,
        "provider_production_ready": descriptor.production_ready,
    }
    if descriptor.warning:
        payload["provider_warning"] = descriptor.warning
    return payload
