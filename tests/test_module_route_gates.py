"""SEC-63/BIZ-61 (разд. 61.3): КАЖДЫЙ роут модуля гейтится — статический сторож.

ТЗ (разд. 61.3, слой «Backend (API-guard)»): «Каждый роут модуля проверяет
entitlement до бизнес-логики». Ратчет-гард ``scripts/ci/check_module_gates.py``
стережёт это на уровне МОДУЛЕЙ (у каждого модуля каталога есть хоть один гейт),
но не на уровне РОУТОВ — и per-route гейт забывали дважды: ``GET /medical/exams``
(список осмотров был виден арендатору без выданного модуля) и
``POST /medical/requirements`` (мутация!); у подрядчиков открытыми стояли
11 роутов — реестр, работники, инциденты, сводка.

Этот сторож закрывает уровень роутов. Гейт признаётся одним из трёх способов:

1. роутерная зависимость: ``router.dependencies.append(Depends(<гейт>))`` —
   покрывает каждый роут файла по построению (самый надёжный, забыть нельзя);
2. per-route: ``dependencies=[<Гейт>]`` в декораторе;
3. вызов гейта в теле функции (стиль модуля импорта).

Список файлов и имена гейтов — явная таблица: новый модульный роутер обязан
добавить сюда строку, иначе его негейченные роуты никто не ищет. Обратной
проверки протухания не нужно: исчезни файл или гейт — тест упадёт сам.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]

#: файл → (маркер роутерной зависимости, имена per-route/inline гейтов)
MODULE_ROUTER_FILES: dict[str, tuple[str | None, tuple[str, ...]]] = {
    "backend/app/api/routes/medical/exams.py": ("_common", ()),
    "backend/app/api/routes/medical/catalog.py": ("_common", ()),
    "backend/app/api/routes/medical/contingent.py": ("_common", ()),
    "backend/app/api/routes/medical/psychiatric.py": ("_common", ()),
    "backend/app/modules/fire_safety/api.py": (
        "router.dependencies.append(Depends(_require_fire_safety))",
        (),
    ),
    # Дрейф, найденный срезом-2 контура БДД (Доп. №1 разд. 56.2): четыре
    # модульных роутера подряд — экология, ГО-ЧС, промбез и БДД — гейт в коде
    # поставили, а строку СЮДА не добавили. Дыры это не создало (гейт
    # роутерный, покрывает каждый роут файла по построению), но сторож за ними
    # не следил: убери кто-нибудь эту строку из кода — и никто бы не заметил.
    # Сторож обязан расти вместе с продуктом, иначе он стережёт вчерашний.
    "backend/app/modules/ecology/api.py": (
        "router.dependencies.append(Depends(_require_ecology))",
        (),
    ),
    "backend/app/modules/civil_defense/api.py": (
        "router.dependencies.append(Depends(_require_civil_defense))",
        (),
    ),
    "backend/app/modules/industrial_safety/api.py": (
        "router.dependencies.append(Depends(_require_industrial_safety))",
        (),
    ),
    "backend/app/modules/road_safety/api.py": (
        "router.dependencies.append(Depends(_require_road_safety))",
        (),
    ),
    "backend/app/api/routes/contractors.py": (
        "router.dependencies.append(Depends(require_contractors_feature))",
        (),
    ),
    "backend/app/api/routes/committees.py": (
        "router.dependencies.append(Depends(_require_committees_enabled))",
        (),
    ),
    "backend/app/api/routes/sout.py": (
        "router.dependencies.append(Depends(_require_sout_enabled))",
        (),
    ),
    "backend/app/api/routes/managed_clients.py": (
        "router.dependencies.append(Depends(_require_enabled))",
        (),
    ),
    "backend/app/modules/budget/api.py": (None, ("FeatureGate",)),
    "backend/app/modules/budget/reimbursement_api.py": (None, ("FeatureGate",)),
    "backend/app/modules/report_builder/api.py": (None, ("FeatureGate",)),
    "backend/app/modules/rules_engine/api.py": (None, ("FeatureGate",)),
    "backend/app/modules/imports/api.py": (None, ("_require_enabled",)),
}

#: файлы, чьи роуты покрыты роутерной зависимостью ОБЩЕГО router из _common
_MEDICAL_COMMON = REPO / "backend/app/api/routes/medical/_common.py"


def _route_defs(path: pathlib.Path) -> list[tuple[str, ast.AsyncFunctionDef | ast.FunctionDef]]:
    """(текст декоратора, функция) для каждого @router.<method>-роута файла."""

    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    out: list[tuple[str, ast.AsyncFunctionDef | ast.FunctionDef]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for deco in node.decorator_list:
            if (
                isinstance(deco, ast.Call)
                and isinstance(deco.func, ast.Attribute)
                and isinstance(deco.func.value, ast.Name)
                and deco.func.value.id == "router"
                and deco.func.attr in {"get", "post", "patch", "put", "delete"}
            ):
                out.append((ast.get_source_segment(text, deco) or "", node))
    return out


def _body_calls(fn: ast.AsyncFunctionDef | ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for inner in ast.walk(fn):
        if isinstance(inner, ast.Call):
            if isinstance(inner.func, ast.Name):
                names.add(inner.func.id)
            elif isinstance(inner.func, ast.Attribute):
                names.add(inner.func.attr)
    return names


@pytest.mark.parametrize("rel", sorted(MODULE_ROUTER_FILES), ids=lambda r: r)
def test_каждый_роут_модуля_гейтится(rel: str) -> None:
    path = REPO / rel
    assert path.exists(), f"{rel}: файл исчез — обнови таблицу сторожа"
    marker, gate_names = MODULE_ROUTER_FILES[rel]

    if marker == "_common":
        # весь файл висит на общем router медицины — гейт обязан стоять там
        common = _MEDICAL_COMMON.read_text(encoding="utf-8")
        assert (
            "router.dependencies.append(Depends(require_medical_feature))" in common
        ), "роутерный гейт медицины снят — все файлы medical/ остались без защиты"
        text = path.read_text(encoding="utf-8")
        assert (
            "from ._common import" in text or "from app.api.routes.medical._common import" in text
        )
        return

    if marker is not None:
        text = path.read_text(encoding="utf-8")
        assert marker in text, f"{rel}: роутерная зависимость гейта снята"
        return

    # per-route / inline: каждый роут обязан нести гейт сам
    ungated = []
    for deco_src, fn in _route_defs(path):
        if any(g in deco_src for g in gate_names):
            continue
        if _body_calls(fn) & set(gate_names):
            continue
        ungated.append(fn.name)
    assert not ungated, (
        f"{rel}: роуты без гейта модуля: {ungated} — разд. 61.3 требует гейт "
        f"на КАЖДОМ роуте (добавь dependencies=[...] или вызов гейта в теле)"
    )


def test_таблица_не_протухла() -> None:
    """Все файлы таблицы существуют; медицина держит общий router."""

    assert _MEDICAL_COMMON.exists()
    for rel in MODULE_ROUTER_FILES:
        assert (REPO / rel).exists(), rel
