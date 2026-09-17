"""Инструменты витрины: пины не откатываются ниже мажора с починкой (срез-220).

ЧТО БЫЛО. Две записи-исключения со сроком 30.09.2026 держали `vitest` 1.x
(GHSA-5xrq-8626-4rwp — чтение и выполнение файлов через UI-сервер) и `vite` 5.x
(GHSA-fx2h-pf6j-xcff — обход `server.fs.deny`). Починка — мажорный подъём всей
цепочки сборки и тестов витрины.

ЧТО ДЕРЖИТ ЭТОТ СТОРОЖ. `vite` не ниже 8, `vitest` и `@vitest/coverage-v8` не
ниже 4 и одной линейки; lock не содержит старых линеек; записи-исключения
убранных уязвимостей не висят до срока. Сторож читает `package.json` и
`package-lock.json` — то, что ставится, а не то, что помнится.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = REPO_ROOT / "frontend"


def _major(spec: str) -> int:
    match = re.search(r"(\d+)\.", spec)
    assert match, spec
    return int(match.group(1))


def _dev_deps() -> dict[str, str]:
    data = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    return data["devDependencies"]


def _locked(name: str) -> str:
    lock = json.loads((FRONTEND / "package-lock.json").read_text(encoding="utf-8"))
    return lock["packages"][f"node_modules/{name}"]["version"]


def test_vite_не_ниже_восьмёрки() -> None:
    assert _major(_dev_deps()["vite"]) >= 8
    assert _major(_locked("vite")) >= 8


def test_vitest_и_покрытие_одной_линейки_не_ниже_четвёртой() -> None:
    """`@vitest/coverage-v8` требует ровно свою версию vitest — разъехаться нельзя."""

    deps = _dev_deps()
    assert _major(deps["vitest"]) >= 4
    assert _locked("vitest") == _locked("@vitest/coverage-v8"), (
        _locked("vitest"),
        _locked("@vitest/coverage-v8"),
    )


def test_исключения_убранных_уязвимостей_сняты() -> None:
    text = (REPO_ROOT / ".github" / "security-exceptions.yml").read_text(encoding="utf-8")
    assert "GHSA-5xrq-8626-4rwp" not in text
    assert "GHSA-fx2h-pf6j-xcff" not in text
