"""Мёртвые инструменты разработки не возвращаются (срезы 218–222).

ЧТО БЫЛО. В манифестах жили инструменты, которых никто не звал: `black` (не
стоял ни в одном гейте), `schemathesis` (только шим), `eslint-plugin-import`
(не был в конфиге eslint), `isort` (ruff-правило `I` заменил), `rollup`,
`ts-node`, `tsconfig-paths` (ни один скрипт и ни один конфиг витрины). Каждый
из них — либо запись-исключение со сроком, либо лишние пакеты в аудите, либо
просто зависимость, которую однажды придётся поднимать «потому что уязвимость».

ЧТО ДЕРЖИТ ЭТОТ СТОРОЖ. Ни один из них не возвращается в манифесты, пока его
никто не зовёт. Если инструмент понадобится — его подключают В ГЕЙТ или В
КОНФИГ, и тогда этот список правят осознанно, с причиной.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Бэкенд: имя пакета в requirements*.txt.
DEAD_PYTHON_TOOLS = ("black", "schemathesis", "isort")
#: Витрина: имя пакета в package.json (dependencies + devDependencies).
#:
#: СРЕЗ-229: сюда добавился `vite-tsconfig-paths`. Он был ЖИВЫМ и служил
#: доказательством, что сторож различает близкие имена: мёртвый
#: `tsconfig-paths` и живой `vite-tsconfig-paths`. С vite 8 его работу делает
#: сам сборщик (`resolve.tsconfigPaths`), и плагин стал лишней зависимостью.
DEAD_NODE_TOOLS = (
    "rollup",
    "ts-node",
    "tsconfig-paths",
    "eslint-plugin-import",
    "vite-tsconfig-paths",
)
#: Живой сосед с похожим именем — его наличие подтверждает, что сторож смотрит
#: точно. После среза-229 это `vite-plugin-pwa`: имя тоже начинается на `vite-`,
#: и его снимать никто не собирался.
LIVE_NODE_TOOL = "vite-plugin-pwa"


def _python_pins() -> set[str]:
    names: set[str] = set()
    for rel in ("requirements.txt", "requirements-dev.txt"):
        for line in (REPO_ROOT / rel).read_text(encoding="utf-8").splitlines():
            match = re.match(r"^([A-Za-z0-9_.-]+)\s*==", line.strip())
            if match:
                names.add(match.group(1).lower())
    return names


def _node_deps() -> dict[str, str]:
    data = json.loads((REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    return {**data.get("dependencies", {}), **data.get("devDependencies", {})}


def test_мёртвые_python_инструменты_не_в_пинах() -> None:
    pins = _python_pins()
    assert pins, "пины не прочитаны"
    for name in DEAD_PYTHON_TOOLS:
        assert name not in pins, f"{name} вернулся в requirements — кто его зовёт?"


def test_мёртвые_node_инструменты_не_в_манифесте() -> None:
    deps = _node_deps()
    for name in DEAD_NODE_TOOLS:
        assert name not in deps, f"{name} вернулся в package.json — кто его зовёт?"


def test_сторож_различает_живого_соседа() -> None:
    """Сторож смотрит на ТОЧНОЕ имя, а не на похожее начало.

    Проверка дословно ловила бы подмену «снять всё, что начинается на `vite-`».
    """

    assert LIVE_NODE_TOOL in _node_deps()
