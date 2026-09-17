"""Инструменты витрины: пины не откатываются ниже мажора с починкой (срезы 220–221).

ЧТО БЫЛО. Пять записей-исключений со сроком 30.09.2026 держали `vitest` 1.x
(GHSA-5xrq-8626-4rwp — чтение и выполнение файлов через UI-сервер), `vite` 5.x
(GHSA-fx2h-pf6j-xcff — обход `server.fs.deny`) и три ReDoS в `minimatch`
9.0.0–9.0.6 (GHSA-3ppc-4f35-3m26, GHSA-7r86-cg39-jmmj, GHSA-23c5-xmqv-rm74).
Записи про minimatch обещали «мажорный подъём eslint», а сверка показала:
уязвимую линейку тянул только `@typescript-eslint/typescript-estree` 6 — хватило
подъёма `@typescript-eslint/*` до 8 без смены eslint и без flat-config.

ЧТО ДЕРЖИТ ЭТОТ СТОРОЖ. `vite` не ниже 8, `vitest` и `@vitest/coverage-v8` не
ниже 4 и одной линейки, `@typescript-eslint/*` не ниже 8; lock не содержит
уязвимой линейки minimatch; мёртвый `eslint-plugin-import` (в конфиге не
использовался) не возвращается; записи-исключения убранных уязвимостей не висят
до срока. Сторож читает `package.json` и `package-lock.json` — то, что ставится,
а не то, что помнится.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = REPO_ROOT / "frontend"

#: minimatch 9.0.0–9.0.6 — три ReDoS; починка — 9.0.7 и выше.
_MINIMATCH_BAD = re.compile(r"^9\.0\.[0-6]$")


def _major(spec: str) -> int:
    match = re.search(r"(\d+)\.", spec)
    assert match, spec
    return int(match.group(1))


def _dev_deps() -> dict[str, str]:
    data = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    return data["devDependencies"]


def _lock_packages() -> dict[str, dict]:
    lock = json.loads((FRONTEND / "package-lock.json").read_text(encoding="utf-8"))
    return lock["packages"]


def _locked(name: str) -> str:
    return _lock_packages()[f"node_modules/{name}"]["version"]


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


def test_typescript_eslint_не_ниже_восьмёрки() -> None:
    """Шестёрка тянула уязвимый minimatch; откат вернул бы три ReDoS без записи."""

    deps = _dev_deps()
    for name in ("@typescript-eslint/parser", "@typescript-eslint/eslint-plugin"):
        assert _major(deps[name]) >= 8, (name, deps[name])
        assert _major(_locked(name)) >= 8, (name, _locked(name))


def test_уязвимой_линейки_minimatch_в_lock_нет() -> None:
    """Сторож смотрит в lock целиком: транзитивная копия — та же дыра."""

    bad = {
        path: meta.get("version")
        for path, meta in _lock_packages().items()
        if path.endswith("node_modules/minimatch") and _MINIMATCH_BAD.match(meta.get("version", ""))
    }
    assert not bad, bad


def test_мёртвый_плагин_импорта_не_возвращается() -> None:
    """`eslint-plugin-import` в конфиге eslint не использовался — только тянул зависимости."""

    assert "eslint-plugin-import" not in _dev_deps()


def test_исключения_убранных_уязвимостей_сняты() -> None:
    text = (REPO_ROOT / ".github" / "security-exceptions.yml").read_text(encoding="utf-8")
    for gid in (
        "GHSA-5xrq-8626-4rwp",
        "GHSA-fx2h-pf6j-xcff",
        "GHSA-3ppc-4f35-3m26",
        "GHSA-7r86-cg39-jmmj",
        "GHSA-23c5-xmqv-rm74",
    ):
        assert gid not in text, gid
