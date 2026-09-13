"""Сторож: каждое событие из конструктора правил кто-то действительно публикует.

ЗАЧЕМ. В конструкторе правил человек выбирает событие-спусковой крючок из
каталога. Каталог строится из перечисления типов событий, а не из того, что
в жизни происходит. Поэтому туда легко попадает событие, которого не бывает:
правило собрано, сохранено, выглядит рабочим — и молчит всегда. Понять,
почему оно молчит, из витрины нельзя.

Ровно так было с `edo.sent` (срез-158): отправки в ЭДО в продукте нет вовсе,
все пути отправки отвечают «провайдер не настроен», а крючок предлагался.

КАК ПРОВЕРЯЕТСЯ. Ищем по РАЗБОРУ КОДА, а не по тексту: событие попадает в
ленту только через ``OutboxService.enqueue``. Прямо его зовут редко, чаще
через посредников — функция принимает тип события своим параметром и передаёт
дальше. Поэтому сначала собираем список посредников (пока список растёт),
потом смотрим, какие ``EventType.X`` видны в функциях, которые этих
посредников зовут. Тип события почти всегда кладут в переменную или в
словарь-посредник, поэтому засчитываем все упоминания внутри такой функции —
проверка намеренно СНИСХОДИТЕЛЬНАЯ: лучше пропустить спорный случай, чем
объявить дефектом живой код.

ЧЕГО СТОРОЖ НЕ ЛОВИТ. Он отвечает на вопрос «есть ли вообще код, который это
событие публикует», а не «правильное ли это место». Второе — работа сверки:
так, `edo.status_changed` публиковался задачей индексации файла, и для этого
сторожа всё выглядело благополучно.
"""

from __future__ import annotations

import ast
import pathlib
from collections import defaultdict

from app.modules.rules_engine.catalog import event_catalog
from app.services.events import EventType

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend" / "app"

#: Имена приёмников ленты: дальше них событие уже не передают.
SINK_NAMES = {"enqueue", "enqueue_event", "publish_event", "emit_event"}

#: Событие предлагается в конструкторе, но кода публикации нет — и это
#: осознанное решение. Пусто: каждое такое событие обязано быть либо
#: починено, либо убрано из каталога (см. `EXCLUDED_EVENT_TYPES`).
KNOWN_OFFERED_WITHOUT_PUBLISHER: dict[str, str] = {}


def _trees() -> dict[pathlib.Path, ast.Module]:
    trees: dict[pathlib.Path, ast.Module] = {}
    for file in sorted(BACKEND.rglob("*.py")):
        trees[file] = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
    return trees


def _called_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _params_of(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    args = node.args
    names = {p.arg for p in args.posonlyargs + args.args + args.kwonlyargs}
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    return names


def _event_arg_names(call: ast.Call) -> set[str]:
    """Имена переменных, попавшие в аргумент про тип события."""

    candidates: list[ast.AST] = [
        kw.value for kw in call.keywords if kw.arg in (None, "event_type", "event", "type_")
    ]
    candidates.extend(call.args)
    return {sub.id for node in candidates for sub in ast.walk(node) if isinstance(sub, ast.Name)}


def _event_literals(node: ast.AST) -> set[str]:
    return {
        sub.attr
        for sub in ast.walk(node)
        if isinstance(sub, ast.Attribute)
        and isinstance(sub.value, ast.Name)
        and sub.value.id == "EventType"
    }


def _publisher_names(trees: dict[pathlib.Path, ast.Module]) -> set[str]:
    publishers = set(SINK_NAMES)
    for _ in range(12):
        grew = False
        for tree in trees.values():
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name in publishers:
                    continue
                params = _params_of(node)
                for call in ast.walk(node):
                    if isinstance(call, ast.Call) and _called_name(call.func) in publishers:
                        if _event_arg_names(call) & params:
                            publishers.add(node.name)
                            grew = True
                            break
        if not grew:
            break
    return publishers


def published_event_names() -> dict[str, set[str]]:
    """{имя типа события: файлы, где его публикуют}."""

    trees = _trees()
    publishers = _publisher_names(trees)
    value_to_name = {event.value: event.name for event in EventType}
    published: dict[str, set[str]] = defaultdict(set)

    for file, tree in trees.items():
        rel = str(file.relative_to(REPO_ROOT))

        module_maps: dict[str, set[str]] = {}
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                found = _event_literals(node.value)
                if found:
                    for target in targets:
                        if isinstance(target, ast.Name):
                            module_maps[target.id] = found

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
                continue
            calls = [c for c in ast.walk(node) if isinstance(c, ast.Call)]
            publishing_calls = [c for c in calls if _called_name(c.func) in publishers]
            if not publishing_calls:
                continue

            found = _event_literals(node)
            used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            for name in used & set(module_maps):
                found |= module_maps[name]
            for call in publishing_calls:
                for keyword in call.keywords:
                    if keyword.arg in ("event_type", "event") and isinstance(
                        keyword.value, ast.Constant
                    ):
                        by_value = value_to_name.get(keyword.value.value)
                        if by_value:
                            found.add(by_value)
            for name in found:
                published[name].add(rel)

    return published


def test_разбор_кода_нашёл_публикации() -> None:
    """Слепой разбор — худший враг сторожа: сначала проверяем, что он видит."""

    published = published_event_names()
    assert len(published) > 25, (
        f"публикаций найдено всего {len(published)} — разбор потерял область "
        "(скорее всего, изменилось имя приёмника ленты)"
    )
    # Три образца разной формы записи: прямой литерал, переменная, словарь.
    assert "INCIDENT_CREATED" in published
    assert "CONTRACTOR_READINESS_BLOCKED" in published, "потеряна форма «тип в переменной»"
    assert "CONTRACTOR_DOCUMENT_EXPIRING" in published, "потеряна форма «тип в словаре»"


def test_каждый_крючок_конструктора_правил_кто_то_публикует() -> None:
    published = published_event_names()
    value_to_name = {event.value: event.name for event in EventType}

    offered = {item["event_type"] for item in event_catalog()}
    assert len(offered) > 20, "каталог конструктора пуст — проверка потеряла смысл"

    dead: dict[str, str] = {}
    for value in sorted(offered):
        if value in KNOWN_OFFERED_WITHOUT_PUBLISHER:
            continue
        name = value_to_name.get(value)
        if name is None or name not in published:
            dead[value] = name or "(нет в перечислении)"

    assert not dead, (
        "конструктор правил предлагает события, которых никто не публикует — "
        "правило на них не сработает никогда и человек не поймёт почему:\n"
        + "\n".join(f"  {value} ({name})" for value, name in sorted(dead.items()))
    )


def test_реестр_исключений_не_протух() -> None:
    """Строка-исключение обязана исчезнуть, как только событие стало живым."""

    published = published_event_names()
    value_to_name = {event.value: event.name for event in EventType}
    stale = [
        value
        for value in KNOWN_OFFERED_WITHOUT_PUBLISHER
        if value_to_name.get(value, "") in published
    ]
    assert not stale, f"событие снова публикуется — уберите его из реестра: {stale}"
