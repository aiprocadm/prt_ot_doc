"""SEC-64 (разд. 64.2): антивирус в конвейере загрузок — обязательный gate.

Что закрепляется:

* при ``AV_ENABLED=true`` скан идёт через НАСТОЯЩИЙ clamd, а не через симулятор по
  имени файла (до этого новый конвейер `modules/files` пользовался только
  симулятором, хотя реальный клиент в проекте был);
* **fail-closed**: сбой сканера — это не «чисто». Раньше любая ошибка попадала в
  ветку «иначе» и объявляла непроверенный файл безопасным;
* гард конфигурации отвергает production/staging с выключенным антивирусом.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.files import av
from app.services.clamav import ClamAVError, ClamAVScanOutcome, ClamAVVerdict

REPO_ROOT = Path(__file__).resolve().parents[1]


def _settings(av_enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(av_enabled=av_enabled)


@pytest.fixture()
def sample(tmp_path: Path) -> Path:
    target = tmp_path / "report.docx"
    target.write_bytes(b"PK\x03\x04 payload")
    return target


class _Scanner:
    def __init__(self, outcome=None, error: Exception | None = None) -> None:
        self.outcome = outcome
        self.error = error
        self.calls = 0

    def scan_stream(self, stream):  # noqa: ANN001 - test double
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.outcome


def test_disabled_av_uses_the_name_simulator(sample: Path) -> None:
    """Локальная разработка и набор тестов идут без поднятого clamd."""

    assert av.scan_file(sample, settings=_settings(False)).status == "clean"

    infected = sample.with_name("eicar-test.docx")
    infected.write_bytes(b"x")
    assert av.scan_file(infected, settings=_settings(False)).status == "infected"


def test_enabled_av_calls_the_real_scanner(
    sample: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scanner = _Scanner(ClamAVScanOutcome(status=ClamAVVerdict.CLEAN, raw="OK"))
    monkeypatch.setattr("app.services.clamav.get_clamav_client", lambda: scanner)

    result = av.scan_file(sample, settings=_settings(True))

    assert scanner.calls == 1, "при включённом антивирусе симулятор недопустим"
    assert result.status == "clean"


def test_infected_verdict_carries_the_signature(
    sample: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scanner = _Scanner(
        ClamAVScanOutcome(status=ClamAVVerdict.INFECTED, signature="Eicar-Test", raw="FOUND")
    )
    monkeypatch.setattr("app.services.clamav.get_clamav_client", lambda: scanner)

    result = av.scan_file(sample, settings=_settings(True))

    assert result.status == "infected"
    assert result.signature == "Eicar-Test"


@pytest.mark.parametrize(
    "failure",
    [ClamAVError("clamd unreachable"), OSError("connection refused")],
)
def test_scanner_failure_is_error_not_clean(
    sample: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    """Ключевой инвариант: непроверенный файл НЕ считается безопасным."""

    scanner = _Scanner(error=failure)
    monkeypatch.setattr("app.services.clamav.get_clamav_client", lambda: scanner)

    assert av.scan_file(sample, settings=_settings(True)).status == "error"


def test_unexpected_verdict_is_error(sample: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scanner = _Scanner(ClamAVScanOutcome(status=ClamAVVerdict.ERROR, raw="ERROR"))
    monkeypatch.setattr("app.services.clamav.get_clamav_client", lambda: scanner)

    assert av.scan_file(sample, settings=_settings(True)).status == "error"


# --- гард конфигурации ---------------------------------------------------------------


def _load_gate():
    path = REPO_ROOT / "scripts" / "ci" / "check_av_gate.py"
    spec = importlib.util.spec_from_file_location("check_av_gate", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("app_env", ["development", "test", ""])
def test_gate_skips_outside_deployed_environments(
    app_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("AV_ENABLED", "false")
    assert _load_gate().main([]) == 0


@pytest.mark.parametrize("app_env", ["production", "staging"])
def test_gate_rejects_disabled_av_in_deployed_environments(
    app_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("AV_ENABLED", "false")
    assert _load_gate().main([]) == 1


def test_gate_rejects_enabled_av_without_a_scanner_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AV_ENABLED", "true")
    monkeypatch.setenv("CLAMAV_HOST", "")
    monkeypatch.delenv("CLAMAV_UNIX_SOCKET", raising=False)
    assert _load_gate().main([]) == 1


def test_gate_passes_for_a_complete_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AV_ENABLED", "true")
    monkeypatch.setenv("CLAMAV_HOST", "clamav")
    assert _load_gate().main([]) == 0
