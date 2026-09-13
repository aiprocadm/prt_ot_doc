"""Сторож: витрина не кладёт в тело запроса полей, которых схема не знает (срез-164).

ЗАЧЕМ. Лишнее поле тела сервер молча выбрасывает: человек заполняет его в
форме, жмёт «Сохранить», получает успех — и значение не сохраняется. Отличить
такое от работающей формы по экрану невозможно.

Ровно так вёл себя мастер комплектов: галочка «предварительная проверка без
записи результатов» отправляла `dry_run: true` в обычный запуск. Схема такого
поля не знает, сервер его выбрасывал и создавал НАСТОЯЩИЙ прогон — документы
писались, а человеку показывали «Dry-run запущен». Проверка без записи у
сервера есть отдельной ручкой (`POST /pack-runs:preview`), мастер теперь зовёт
именно её.

КАК ПРОВЕРЯЕТСЯ. Контракт берётся у живого приложения, из витрины читаются
вызовы `apiClient.post|put|patch` с телом-ЛИТЕРАЛОМ. Сверяются только поля
ВЕРХНЕГО уровня: вложенные объекты (`context`, `items`) сервер принимает как
свободные, и заглядывать внутрь нечестно — там своя схема или её нет вовсе.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"

#: Поле, которого схема не знает, но оно осмысленно. Пусто: каждая строка
#: обязана нести причину, иначе это дефект.
KNOWN_EXTRA_FIELDS: dict[str, str] = {}

_CALL_RE = re.compile(
    r"apiClient\.(post|put|patch)<[^>]*>?\(\s*(`[^`]*`|\"[^\"]*\")\s*,\s*\{(.*?)\}\s*[,)]",
    re.S,
)
#: Поле верхнего уровня: ровно один уровень отступа внутри литерала тела.
_TOP_FIELD_RE = re.compile(r"^\s{8}([a-z_][A-Za-z0-9_]*)\s*:", re.M)


def _schema_fields(schema: dict[str, Any], components: dict[str, Any], depth: int = 0) -> set[str]:
    if depth > 4 or not isinstance(schema, dict):
        return set()
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        return _schema_fields(components.get(name, {}), components, depth + 1)
    fields: set[str] = set(schema.get("properties", {}))
    for key in ("allOf", "anyOf", "oneOf"):
        for part in schema.get(key, []):
            fields |= _schema_fields(part, components, depth + 1)
    return fields


@pytest.fixture(scope="module")
def declared() -> dict[tuple[str, str], set[str]]:
    from app.api.app import create_app

    spec = create_app().openapi()
    components = spec.get("components", {}).get("schemas", {})
    bodies: dict[tuple[str, str], set[str]] = {}
    for path, methods in spec.get("paths", {}).items():
        for method, operation in methods.items():
            if method not in {"post", "put", "patch"}:
                continue
            content = (
                operation.get("requestBody", {}).get("content", {}).get("application/json", {})
            )
            fields = _schema_fields(content.get("schema", {}), components)
            if fields:
                bodies[(path, method)] = fields
    return bodies


def _segments(path: str) -> tuple[str, ...]:
    return tuple(part for part in path.strip("/").split("/") if part)


def _matches(call: tuple[str, ...], route: tuple[str, ...]) -> bool:
    if len(call) != len(route):
        return False
    return all(a == b or a.startswith("{") or b.startswith("{") for a, b in zip(call, route))


def _frontend_bodies() -> list[tuple[str, str, str, set[str]]]:
    calls: list[tuple[str, str, str, set[str]]] = []
    files = list(FRONTEND_SRC.rglob("*.ts")) + list(FRONTEND_SRC.rglob("*.tsx"))
    for file in files:
        if ".test." in file.name or "__tests__" in file.parts:
            continue
        text = file.read_text(encoding="utf-8")
        for match in _CALL_RE.finditer(text):
            keys = set(_TOP_FIELD_RE.findall(match.group(3)))
            if not keys:
                continue
            raw_path = match.group(2)[1:-1]
            path = re.sub(r"\$\{[^}]*\}", "{x}", raw_path)
            full = path if path.startswith("/api") else "/api/v1" + path
            calls.append((str(file.relative_to(REPO_ROOT)), match.group(1), full, keys))
    return calls


def test_область_разбора_не_потерялась(declared: dict[tuple[str, str], set[str]]) -> None:
    assert len(declared) > 200, f"ручек с телом всего {len(declared)} — контракт не собрался"
    assert len(_frontend_bodies()) >= 8, "вызовов с телом-литералом почти не найдено"


def test_витрина_не_шлёт_полей_которых_схема_не_знает(
    declared: dict[tuple[str, str], set[str]],
) -> None:
    routes = [(_segments(path), (path, method)) for (path, method) in declared]
    problems: list[str] = []
    recognized = 0

    for file, method, path, keys in _frontend_bodies():
        call = _segments(path)
        known: set[str] = set()
        targets: list[str] = []
        for route_segments, key in routes:
            if key[1] == method and _matches(call, route_segments):
                known |= declared[key]
                targets.append(key[0])
        if not targets:
            continue
        recognized += 1
        unknown = sorted(key for key in keys - known if key not in KNOWN_EXTRA_FIELDS)
        if unknown:
            problems.append(
                f"  {method.upper()} {', '.join(sorted(targets))} — {', '.join(unknown)} — {file}"
            )

    assert recognized >= 5, f"опознано всего {recognized} вызовов — сверка потеряла смысл"
    assert not problems, (
        "витрина кладёт в тело запроса поля, которых схема не знает: сервер их "
        "молча выбрасывает, и форма делает не то, что обещает:\n" + "\n".join(problems)
    )


def test_проверка_комплекта_без_записи_зовёт_свою_ручку() -> None:
    """Галочка «только проверить» обязана вести на ручку, которая не пишет."""

    text = (FRONTEND_SRC / "api" / "packs.ts").read_text(encoding="utf-8")
    # Пояснение в комментарии называет старое поле по имени — считаем только
    # живой код, иначе сторож поймает собственную докстроку.
    live = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith(("//", "*", "/*"))
    )
    assert "/pack-runs:preview" in live, (
        "проверка комплекта без записи снова идёт через обычный запуск — "
        "документы будут записаны, а человеку скажут, что это была проверка"
    )
    assert "dry_run" not in live, "в теле запуска снова появилось поле, которого схема не знает"
