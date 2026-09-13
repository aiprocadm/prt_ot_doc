"""Сторож: витрина не шлёт параметров запроса, которых ручка не знает (срез-163).

ЗАЧЕМ. Лишний параметр — не ошибка и не отказ: сервер его молча выбрасывает.
На экране от этого остаётся фильтр, который стоит на месте. Человек двигает
выбор, список не меняется, и понять причину нельзя — ответ приходит успешный.

Это соседний класс к сторожу путей (`test_frontend_api_paths.py`, срез-152):
там витрина звала несуществующую ручку и получала 404, здесь зовёт
существующую, но просит у неё то, чего та не понимает.

КАК ПРОВЕРЯЕТСЯ. Контракт берётся у живого приложения (там же, где его берёт
снимок OpenAPI), из витрины читаются вызовы `apiClient.*` с объектом
`params`. Путь приводится к виду контракта (подстановка — любой сегмент).
Сверяются только параметры, записанные ЛИТЕРАЛОМ: то, что собрано в
переменной, разбор честно пропускает.

Пути сравниваются посегментно, и подстановка сходится с любым сегментом — с
ОБЕИХ сторон. Это важно: витрина часто подставляет туда, где у сервера
постоянный кусок (`/analytics/trends/${metric}` против трёх отдельных ручек
`.../incidents`, `.../inspections`, `.../ppe`). Когда таких ручек несколько,
берём объединение их параметров: вызов уходит к одной из них, и любой из этих
наборов законен.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"

#: Параметр, который сервер и правда не объявляет, но он осмыслен. Пусто:
#: каждая такая строка обязана нести причину, иначе это дефект.
KNOWN_EXTRA_PARAMS: dict[str, str] = {}

_CALL_RE = re.compile(
    r"apiClient\.(get|post|put|patch|delete)<[^>]*>?\(\s*(`[^`]*`|\"[^\"]*\")(.*?)\)\s*;",
    re.S,
)
_PARAMS_RE = re.compile(r"params:\s*\{(.*?)\}", re.S)
_KEY_RE = re.compile(r"([a-z_][A-Za-z0-9_]*)\s*:", re.M)


def _declared_query_params() -> dict[str, dict[str, set[str]]]:
    from app.api.app import create_app

    spec = create_app().openapi()
    declared: dict[str, dict[str, set[str]]] = {}
    for path, methods in spec.get("paths", {}).items():
        for method, operation in methods.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            names = {
                parameter["name"]
                for parameter in operation.get("parameters", [])
                if parameter.get("in") == "query"
            }
            declared.setdefault(path, {})[method] = names
    return declared


def _segments(path: str) -> tuple[str, ...]:
    return tuple(part for part in path.strip("/").split("/") if part)


def _matches(call: tuple[str, ...], route: tuple[str, ...]) -> bool:
    """Подстановка (`{...}`) сходится с любым сегментом с обеих сторон."""

    if len(call) != len(route):
        return False
    return all(a == b or a.startswith("{") or b.startswith("{") for a, b in zip(call, route))


def _frontend_calls() -> list[tuple[str, str, str, set[str]]]:
    """(файл, метод, путь, параметры) для вызовов с объектом `params`."""

    calls: list[tuple[str, str, str, set[str]]] = []
    files = list(FRONTEND_SRC.rglob("*.ts")) + list(FRONTEND_SRC.rglob("*.tsx"))
    for file in files:
        if ".test." in file.name or "__tests__" in file.parts:
            continue
        text = file.read_text(encoding="utf-8")
        for match in _CALL_RE.finditer(text):
            params_match = _PARAMS_RE.search(match.group(3))
            if not params_match:
                continue
            keys = set(_KEY_RE.findall(params_match.group(1)))
            if not keys:
                continue
            raw_path = match.group(2)[1:-1]
            path = re.sub(r"\$\{[^}]*\}", "{x}", raw_path)
            full = path if path.startswith("/api") else "/api/v1" + path
            calls.append((str(file.relative_to(REPO_ROOT)), match.group(1), full, keys))
    return calls


@pytest.fixture(scope="module")
def declared() -> dict[str, dict[str, set[str]]]:
    return _declared_query_params()


def test_область_разбора_не_потерялась(declared: dict[str, dict[str, set[str]]]) -> None:
    assert len(declared) > 500, f"ручек в контракте всего {len(declared)} — контракт не собрался"
    calls = _frontend_calls()
    assert (
        len(calls) > 40
    ), f"вызовов с параметрами найдено всего {len(calls)} — разбор витрины потерял область"


def test_витрина_не_шлёт_неизвестных_ручке_параметров(
    declared: dict[str, dict[str, set[str]]],
) -> None:
    routes = [(_segments(path), path) for path in declared]
    problems: list[str] = []
    recognized = 0

    for file, method, path, keys in _frontend_calls():
        call = _segments(path)
        targets = [original for segments, original in routes if _matches(call, segments)]
        if not targets:
            continue  # путь сверяет сторож путей API, здесь он не наша забота
        recognized += 1
        known: set[str] = set()
        for target in targets:
            known |= declared[target].get(method, set())
        unknown = sorted(key for key in keys - known if key not in KNOWN_EXTRA_PARAMS)
        if unknown:
            problems.append(
                f"  {method.upper()} {', '.join(sorted(targets))} — {', '.join(unknown)} "
                f"(ручка принимает: {', '.join(sorted(known)) or 'ничего'}) — {file}"
            )

    assert recognized > 30, f"опознано всего {recognized} вызовов — сверка потеряла смысл"
    assert not problems, (
        "витрина шлёт параметры, которых ручка не объявляет: сервер их молча "
        "выбрасывает, и фильтр на экране не работает, не сообщая об этом:\n" + "\n".join(problems)
    )


def test_реестр_исключений_не_протух() -> None:
    """Пустой реестр — норма; строка в нём обязана нести причину."""

    for param, reason in KNOWN_EXTRA_PARAMS.items():
        assert reason.strip(), f"у исключения {param} нет причины"
