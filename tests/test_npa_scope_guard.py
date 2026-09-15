"""Сторож: акты спрашивают ТОЛЬКО через фильтр видимости (срез-201).

ПОЧЕМУ ЭТОТ СТОРОЖ ВООБЩЕ НУЖЕН. С срезом-201 в общей таблице ``npa_act``
лежат две разные вещи: федеральные акты (``owner_tenant_id IS NULL``, видны
всем) и собственные приказы арендаторов (видны только своему). Таблица общая,
она вне схемы арендатора, и RLS к ней неприложим — строка с NULL обязана быть
видна всем. Значит, у изоляции здесь ОДИН рубеж: условие в запросе.

Один рубеж — это ровно одна забытая строка до утечки. Поэтому правило сделано
машинным: прямые ``select(NpaAct)`` и ``session.get(NpaAct, ...)`` запрещены
везде, кроме самого ``app/domains/npa/scope.py``. Хочешь акты — иди через
``visible_acts()`` или ``get_visible_act()``, и фильтр приедет сам.

ЧЕМ ЭТОТ СТОРОЖ НЕ ЯВЛЯЕТСЯ. Он читает ТЕКСТ исходников и потому видит только
знакомые формы записи. Он не поймает запрос, собранный через переменную. Это
не делает его бесполезным: он ловит ту форму, которой пишут в этом репозитории
все девять прежних мест, и не даёт появиться десятому по привычке. Настоящую
изоляцию проверяет ``tests/api/test_npa_tenant_acts.py`` — живыми запросами от
двух арендаторов.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/test_npa_scope_guard.py -v``.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend" / "app"

#: Единственное место, которому можно спрашивать акты напрямую: там и живёт
#: само условие видимости.
SCOPE_MODULE = BACKEND / "domains" / "npa" / "scope.py"

#: Модели описывают таблицу, а не спрашивают её.
ALLOWED = frozenset({SCOPE_MODULE, BACKEND / "models" / "npa.py"})


def _direct_queries(tree: ast.AST) -> list[tuple[int, str]]:
    """Находит ``select(NpaAct...)`` и ``<что-то>.get(NpaAct, ...)``.

    Обе формы опасны одинаково, но по-разному: ``select`` забывает условие, а
    ``session.get`` условий не принимает ВООБЩЕ — он берёт строку по первичному
    ключу, а ключ приходит из запроса пользователя.
    """

    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Name) and first.id == "NpaAct"):
            # `select(NpaAct.id)` — тоже выборка из таблицы актов.
            if not (
                isinstance(first, ast.Attribute)
                and isinstance(first.value, ast.Name)
                and first.value.id == "NpaAct"
            ):
                continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in {"select", "get"}:
            found.append((node.lineno, name))
    return found


def test_акты_спрашивают_только_через_фильтр_видимости() -> None:
    offenders: list[str] = []
    for path in sorted(BACKEND.rglob("*.py")):
        if path in ALLOWED:
            continue
        source = path.read_text(encoding="utf-8")
        if "NpaAct" not in source:
            continue
        for lineno, kind in _direct_queries(ast.parse(source)):
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno} — {kind}(NpaAct...)")

    assert not offenders, (
        "Акты спрошены мимо app/domains/npa/scope.py — в общей таблице лежат и "
        "собственные приказы арендаторов, и без фильтра их увидит чужой:\n  "
        + "\n  ".join(offenders)
        + "\nВозьмите visible_acts(tenant_id) или get_visible_act(session, id, tenant_id)."
    )


def test_сторож_ловит_нарушение() -> None:
    """Доказано поломкой: без этой проверки предыдущий тест зелен всегда.

    Разбор по тексту исходника — самый лживый вид сторожа: он молчит и когда
    всё хорошо, и когда сам сломан.
    """

    bad = ast.parse("acts = await session.execute(select(NpaAct).order_by(NpaAct.code))")
    assert _direct_queries(bad) == [(1, "select")]

    bad_get = ast.parse("act = await session.get(NpaAct, act_id)")
    assert _direct_queries(bad_get) == [(1, "get")]

    bad_column = ast.parse("act_id = await session.scalar(select(NpaAct.id))")
    assert _direct_queries(bad_column) == [(1, "select")]

    good = ast.parse("acts = await session.execute(visible_acts(tenant_id).order_by(NpaAct.code))")
    assert _direct_queries(good) == []


def test_фильтр_видимости_живёт_ровно_в_одном_месте() -> None:
    """Условие «моё или общее» не должно размножиться по коду.

    Разъехавшись, «мой акт» начал бы означать разное в списке и в правке — и
    расхождение нашли бы не тестом, а чужим приказом на экране.
    """

    assert SCOPE_MODULE.exists()
    hits = [
        path.relative_to(REPO_ROOT)
        for path in sorted(BACKEND.rglob("*.py"))
        if path != SCOPE_MODULE and "owner_tenant_id.is_(None)" in path.read_text(encoding="utf-8")
    ]
    assert not hits, f"условие видимости повторено вне scope.py: {hits}"
