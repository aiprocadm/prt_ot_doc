"""Инструменты тестов: живые версии закреплены, мёртвые не возвращаются (срез-219).

ЧТО БЫЛО. `pytest` 8.3 держал запись-исключение PYSEC-2026-1845 со сроком
30.09.2026, а «починка» значилась как мажорный подъём, который «тянет
совместимость плагинов». Сверка показала: своих `event_loop`-фикстур в тестах
нет, хуков `pytest_*` нет, устаревших API (`tmpdir`, `py.path`,
`pytest.warns(None)`) нет — подъём безопасен. А `schemathesis`, который
пинил потолок `pytest`, в тестах не использовался вовсе: жил только шимом в
`sitecustomize.py`, и в окружении стояла 3.28 при пине 4.10 — этого никто не
заметил. Он убран так же, как `black` в срезе-218.

ЧТО ДЕРЖИТ ЭТОТ СТОРОЖ. Пины не откатываются ниже мажора с починкой; мёртвый
инструмент не возвращается ни в пины, ни в шим; запись-исключение убранной
уязвимости не висит до срока.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _pins() -> dict[str, tuple[int, ...]]:
    text = (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    pins: dict[str, tuple[int, ...]] = {}
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==([0-9.]+)", line.strip())
        if match:
            pins[match.group(1).lower()] = tuple(int(p) for p in match.group(2).split("."))
    return pins


def test_pytest_не_ниже_девятки() -> None:
    """Откат к 8.x вернул бы открытую уязвимость без записи-исключения."""

    pins = _pins()
    assert pins["pytest"] >= (9,), pins.get("pytest")
    assert pins["pytest-asyncio"] >= (1,), pins.get("pytest-asyncio")


def test_живой_pytest_совпадает_с_пином() -> None:
    """Пин без установки — обещание; аудит проверяет установленное окружение."""

    pins = _pins()
    installed = tuple(int(p) for p in pytest.__version__.split(".")[:3])
    assert installed[:2] == pins["pytest"][:2], (installed, pins["pytest"])


def test_schemathesis_не_возвращается() -> None:
    """Инструмент, который никто не звал, держал потолок pytest — назад нельзя."""

    text = (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "schemathesis" not in text
    shim = (REPO_ROOT / "sitecustomize.py").read_text(encoding="utf-8")
    assert "schemathesis" not in shim, "шим schemathesis снова в sitecustomize"


def test_исключение_убранной_уязвимости_снято() -> None:
    text = (REPO_ROOT / ".github" / "security-exceptions.yml").read_text(encoding="utf-8")
    assert "PYSEC-2026-1845" not in text
