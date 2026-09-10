"""Тесты не ломаются о полночь (BIZ-54-57 срез-129).

ЗАЧЕМ. Полный набор идёт почти три часа, и запуск вечером ЗАКАНЧИВАЕТСЯ уже
следующим днём. Проверка вида ``assert ответ == str(date.today())`` в такой
прогон падает: сервер посчитал дату до полуночи, проверка — после. Падение
выглядит как поломка продукта, хотя продукт исправен.

Цена не в самих падениях, а в том, что к ним привыкают. Полный прогон
2026-09-08 дал три красных: два таких «полуночных» и один НАСТОЯЩИЙ — сторож
формулы «допущенный водитель» был красным на `main` с среза-123 и никем не
замечен, потому что срезы 123–126 закрывались прицельной регрессией. Красный
прогон, в котором «эти два всегда падают», перестаёт быть сигналом вообще.

ЧТО ПРОВЕРЯЕТСЯ: ни одна проверка НА РАВЕНСТВО не вычисляет «сейчас» внутри
себя. Дату надо взять один раз в переменную (и отправить, и сверить её же)
либо запомнить до и после запроса и принять любой из двух дней. Сравнения на
«больше/меньше» разрешены: они от смены суток не портятся.

ЧЕГО СТОРОЖ НЕ ВИДИТ (срез-140): РАЗНЫЕ ЧАСЫ у проверки и у продукта. Процесс
тестов живёт по Москве (``DEFAULT_TIMEZONE`` через ``time.tzset``), и
``date.today()`` в нём — московская дата; контур дисциплин считает день по
UTC. С 21:00 до 24:00 UTC это разные даты, и «до/после» не спасает: обе
взяты не теми часами. Полный прогон 2026-09-10 (20:46–23:45 UTC) дал два
таких красных — и те же два на ``main`` в то же окно. Правило: дату для
сверки с ответом сервера брать ТЕМИ ЖЕ часами, что у сервера (в тестах
дисциплин — ``server_today()``). Машиной это не проверить: какими часами
считает продукт, видно только из его кода.
"""

from __future__ import annotations

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
TEST_ROOTS = ("tests", "backend/tests", "integration_tests")

#: Вызовы, дающие «сейчас». Список закрыт: своя обёртка над временем — повод
#: вписать её сюда осознанно, а не расширять шаблон.
NOW_CALLS = {("date", "today"), ("datetime", "now"), ("datetime", "utcnow")}

#: Проверки, где «сейчас» внутри равенства оставлено ОСОЗНАННО. Пусто: все
#: найденные починены. Реестр оставлен потому, что запрет не абсолютный —
#: но причина обязана быть названа словами.
NAMED_EXCEPTIONS: dict[str, str] = {}


def _is_now_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return (func.value.id, func.attr) in NOW_CALLS
    return False


def _offenders() -> list[str]:
    found: list[str] = []
    for root in TEST_ROOTS:
        base = REPO / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover — синтаксис ловит сам pytest
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assert):
                    continue
                for comparison in ast.walk(node):
                    if not isinstance(comparison, ast.Compare):
                        continue
                    equality = any(
                        isinstance(op, (ast.Eq, ast.NotEq, ast.In, ast.NotIn))
                        for op in comparison.ops
                    )
                    if not equality:
                        continue
                    if any(_is_now_call(inner) for inner in ast.walk(comparison)):
                        rel = path.relative_to(REPO).as_posix()
                        found.append(f"{rel}:{node.lineno}")
                        break
    return found


def test_сторож_нашлось_бы_хоть_что_то() -> None:
    """Разбор должен уметь находить нарушение — иначе сторож зелен впустую."""

    sample = ast.parse('assert body["day"] == str(date.today())\n')
    node = sample.body[0]
    assert isinstance(node, ast.Assert)
    assert any(_is_now_call(inner) for inner in ast.walk(node)), "разбор перестал узнавать «сейчас»"


def test_проверки_на_равенство_не_считают_сейчас_заново() -> None:
    """«Сегодня» у сервера и у проверки — это два РАЗНЫХ вычисления."""

    offenders = [item for item in _offenders() if item not in NAMED_EXCEPTIONS]
    assert offenders == [], (
        "проверка на равенство вычисляет «сейчас» внутри себя и упадёт, если "
        "прогон пересечёт полночь — возьмите дату один раз в переменную либо "
        f"запомните её до и после запроса: {offenders}"
    )


def test_реестр_исключений_не_протухает() -> None:
    """Названное исключение, которого в коде нет, — мёртвая строка реестра."""

    live = set(_offenders())
    stale = sorted(name for name in NAMED_EXCEPTIONS if name not in live)
    assert stale == [], f"реестр исключений разошёлся с кодом: {stale}"
