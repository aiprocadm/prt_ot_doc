from __future__ import annotations

from app.services.provider_registry import describe_provider, provider_response_meta


def test_stub_provider_marked_as_non_production() -> None:
    descriptor = describe_provider("stub-edo")

    assert descriptor.mode == "non_production"
    assert descriptor.production_ready is False
    assert "non-production mode" in (descriptor.warning or "")


def test_unknown_named_provider_remains_production_candidate() -> None:
    descriptor = describe_provider("kontur-diadoc")

    assert descriptor.mode == "production_candidate"
    assert descriptor.production_ready is True
    assert descriptor.warning is None


def test_provider_response_meta_is_additive_and_stable() -> None:
    payload = provider_response_meta("mock")

    assert payload["provider_code"] == "mock"
    assert payload["provider_mode"] == "non_production"
    assert payload["provider_production_ready"] is False
    assert "provider_warning" in payload


def test_internal_fallback_provider_marked_as_non_production() -> None:
    descriptor = describe_provider("internal-fallback")

    assert descriptor.mode == "non_production"
    assert descriptor.production_ready is False
