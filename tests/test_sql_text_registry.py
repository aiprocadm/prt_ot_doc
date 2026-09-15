"""SEC-64, разд. 64.1, строка «Injection»: реестр мест, где SQL собирается из кусков.

ЗАЧЕМ РЕЕСТР. Правило «запросы параметризованы» проверить одним взглядом нельзя:
имя таблицы или схемы параметром не передашь, поэтому склейка местами
НЕИЗБЕЖНА. Значит, вопрос не «есть ли склейка», а «каждое ли место склейки
объяснено и защищено». Реестр отвечает на второй вопрос и краснеет, когда
появляется место, которого в нём нет.

РАЗБОР ПО КОДУ, А НЕ ПО ТЕКСТУ. Срез-206 оставил записанный урок: сторож,
который ищет подстроку в исходнике, считает живым вызов в мёртвой ветке и не
видит вызова, написанного иначе. Поэтому здесь читается ДЕРЕВО РАЗБОРА (AST):
находится вызов ``text``/``execute``, и смотрится, собран ли его первый
аргумент из кусков — f-строкой, сложением или ``format``/``join``.

ЧТО СЧИТАЕТСЯ ЗАКОННЫМ МЕСТОМ. Только имя объекта базы (схема, таблица,
колонка), пришедшее из нашего же реестра или снятое с самой базы, и только
через ``quote_identifier`` из ``app/core/sql_text.py`` — он проверяет формат и
ставит кавычки. ЗНАЧЕНИЕ склеивать нельзя никогда: для значений есть параметры.

ГРАНИЦА ЭТОГО СТОРОЖА НАЗВАНА ЧЕСТНО. Он видит, ГДЕ собирается SQL, но не
доказывает, что собранное безопасно: это доказывают отдельные проверки ниже —
поведением ``quote_identifier`` на враждебных именах.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.core.sql_text import UnsafeSqlIdentifier, assert_safe_identifier, quote_identifier

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = REPO_ROOT / "backend" / "app"

#: Реестр: файл → почему в нём склеивается SQL. Ключ — путь от корня репозитория.
#: Новое место склейки обязано попасть сюда С ПРИЧИНОЙ, иначе проверка краснеет.
#: Причина пишется словами: «потому что так исторически» — не причина.
ALLOWED_SQL_BUILDERS: dict[str, str] = {
    "backend/app/db/session.py": (
        "Имена схем арендатора в search_path и CREATE SCHEMA. Схема — идентификатор, "
        "параметром не передаётся; имя проходит quote_identifier."
    ),
    "backend/app/modules/offboarding/export.py": (
        "Полный дамп данных арендатора обходит таблицы из реестра RLS_ENABLED_TABLES. "
        "Имя таблицы — идентификатор; значения идут параметрами."
    ),
    "backend/app/modules/offboarding/purge.py": (
        "Удаление и обезличивание данных ушедшего арендатора идут по карте связей, "
        "снятой с самой базы. Имена таблиц и колонок — идентификаторы."
    ),
    "backend/app/modules/offboarding/lifecycle.py": (
        "План удаления считает строки по таблицам из схемы базы. Имя таблицы — идентификатор."
    ),
    "backend/app/modules/offboarding/file_keys.py": (
        "Сбор ключей файлов арендатора перед удалением: имена таблиц и колонок сняты со схемы."
    ),
}

#: Место, где склейка ЗАПРЕЩЕНА и заменена параметром (срез-210). Живёт в реестре
#: отдельной записью, чтобы возврат к склейке был виден в истории, а не потерялся.
FORBIDDEN_NOTE = (
    "Метка сессии (application_name) приходит из заголовка запроса. Склеивалась в "
    "текст SQL, а «обезвреживание» снимало не тот знак кавычки. Теперь — set_config "
    "с настоящим параметром: значение текстом запроса не становится."
)

_BUILDER_CALLS = {"text", "execute", "exec_driver_sql"}


def _is_built_from_pieces(node: ast.expr) -> str | None:
    """Как собран аргумент: f-строкой, сложением, format/join — или он постоянный."""

    if isinstance(node, ast.JoinedStr):
        return "f-строка"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return "склейка +"
    if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in {"format", "join"}:
        return "format/join"
    return None


def _collect_sql_builders() -> dict[str, list[int]]:
    """Все места в приложении, где первый аргумент запроса собран из кусков."""

    found: dict[str, list[int]] = {}
    for path in sorted(APP_ROOT.rglob("*.py")):
        if "migrations" in path.parts:
            # Миграции пишет разработчик руками, пользовательских данных там нет.
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in _BUILDER_CALLS or not node.args:
                continue
            if _is_built_from_pieces(node.args[0]):
                rel = path.relative_to(REPO_ROOT).as_posix()
                found.setdefault(rel, []).append(node.lineno)
    return found


def test_каждое_место_склейки_sql_есть_в_реестре() -> None:
    found = _collect_sql_builders()
    unknown = {path: lines for path, lines in found.items() if path not in ALLOWED_SQL_BUILDERS}
    assert not unknown, (
        "Появились новые места, где SQL собирается из кусков. Если это ИМЯ объекта базы — "
        "проведите его через quote_identifier и впишите файл в ALLOWED_SQL_BUILDERS с причиной. "
        "Если это ЗНАЧЕНИЕ — склейка не нужна, передайте параметром: " + repr(unknown)
    )


def test_реестр_не_хранит_записей_про_исчезнувшие_файлы() -> None:
    """Реестр без уборки превращается в список того, чего давно нет."""

    found = _collect_sql_builders()
    stale = sorted(set(ALLOWED_SQL_BUILDERS) - set(found))
    assert not stale, (
        "В реестре остались файлы, где склейки SQL больше нет — удалите записи: " + repr(stale)
    )


def test_у_каждой_записи_реестра_есть_причина_словами() -> None:
    for path, reason in ALLOWED_SQL_BUILDERS.items():
        assert len(reason) > 40, f"причина для {path} слишком коротка, чтобы что-то объяснить"


def test_метка_сессии_больше_не_склеивается() -> None:
    """Само место дефекта: значение из заголовка уходит параметром.

    Проверка идёт ПО КОДУ: в файле сессий не должно остаться вызова, который
    строит текст с ``application_name``.
    """

    source = (APP_ROOT / "db" / "session.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name not in _BUILDER_CALLS or not node.args:
            continue
        if not _is_built_from_pieces(node.args[0]):
            continue
        fragment = ast.get_source_segment(source, node.args[0]) or ""
        assert "application_name" not in fragment, FORBIDDEN_NOTE


@pytest.mark.parametrize(
    "hostile",
    [
        'tenant"; DROP TABLE users; --',
        "tenant'",
        "tenant name",
        "таблица",
        "",
        "1tenant",
        "t" * 64,
        "tenant\nname",
    ],
)
def test_враждебное_имя_объекта_базы_отвергается(hostile: str) -> None:
    """Проверка формата доказывается ПОВЕДЕНИЕМ, а не наличием строки в коде."""

    with pytest.raises(UnsafeSqlIdentifier):
        quote_identifier(hostile, source="проверка")


def test_обычное_имя_проходит_и_получает_кавычки() -> None:
    # Кавычки нужны и после проверки: имя может совпасть со словом языка запросов.
    assert quote_identifier("tenant_demo", source="проверка") == '"tenant_demo"'
    assert assert_safe_identifier("pdn_breach", source="проверка") == "pdn_breach"


def test_схема_арендатора_с_дефисом_проходит() -> None:
    """Проверка формата не должна сломать НАСТОЯЩИХ арендаторов.

    Слаг описан как ``[a-z][a-z0-9_-]``, схема зовётся ``tenant_<слаг>`` — то
    есть дефис в имени схемы законен. Это поймано до вливания: первая версия
    проверки дефис запрещала и уронила бы такого арендатора на каждом запросе.
    """

    assert quote_identifier("tenant_demo-corp", source="проверка") == '"tenant_demo-corp"'


def test_значение_метки_уходит_параметром_а_не_текстом() -> None:
    """Опасные знаки остаются В ЗНАЧЕНИИ и никак не влияют на текст запроса."""

    from app.core.sql_text import session_label_params, session_label_statement

    hostile = "x'; INSERT INTO t VALUES (1) --"
    statement = str(session_label_statement())
    params = session_label_params(hostile)

    assert "INSERT" not in statement
    assert ":value" in statement
    assert params["value"].endswith(hostile)
