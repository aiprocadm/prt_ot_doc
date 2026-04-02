import locale

import pytest

from app.core import i18n


def test_configure_runtime_locale_accepts_bcp47_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[str] = []

    def fake_setlocale(category: int, value: str | None = None) -> str:
        assert category == locale.LC_ALL
        if value in {None, "C"}:
            return "C"
        attempts.append(value)
        if value == "ru_RU.UTF-8":
            return value
        raise locale.Error("unsupported locale setting")

    def fake_normalize(value: str) -> str:
        if value == "ru_RU":
            return "ru_RU.UTF-8"
        return value

    monkeypatch.setattr(i18n.locale, "setlocale", fake_setlocale)
    monkeypatch.setattr(i18n.locale, "normalize", fake_normalize)

    runtime = i18n.configure_runtime_locale(locale_name="ru-RU", timezone_name="UTC")

    assert attempts == ["ru_RU", "ru_RU.UTF-8"]
    assert runtime.locale_name == "ru_RU.UTF-8"
    assert runtime.timezone.key == "UTC"


def test_configure_runtime_locale_falls_back_to_c(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    attempts: list[str] = []

    def fake_setlocale(category: int, value: str | None = None) -> str:
        assert category == locale.LC_ALL
        chosen = value or "C"
        attempts.append(chosen)
        if chosen == "C":
            return "C"
        raise locale.Error("unsupported locale setting")

    monkeypatch.setattr(i18n.locale, "setlocale", fake_setlocale)
    monkeypatch.setattr(i18n.locale, "normalize", lambda value: value)

    with caplog.at_level("WARNING"):
        runtime = i18n.configure_runtime_locale(locale_name="zz-ZZ", timezone_name="UTC")

    assert runtime.locale_name == "C"
    assert runtime.timezone.key == "UTC"
    assert attempts[-1] == "C"
    assert any("zz-ZZ" in message for message in caplog.messages)
