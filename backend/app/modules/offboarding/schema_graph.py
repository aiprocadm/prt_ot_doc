"""OPS-72 срез-3: граф зависимостей схемы для офбординга.

Здесь живёт то, обо что споткнулся срез-2: **удалить данные арендатора «в
обратном порядке зависимостей» нельзя, пока в схеме есть циклы внешних ключей**
(``document`` ↔ ``documentgenerationjob``, ``medical_exam`` ↔ ``medical_referral``,
``template`` ↔ ``templateversion``). Сортировщик SQLAlchemy на таких таблицах
сдаётся, а удаление, написанное в обход этого факта, стирало бы данные ЧАСТИЧНО
И МОЛЧА — худший исход для необратимой операции.

Два решения, которые стоит держать в голове при ревью:

* **Граф строится отражением ЖИВОЙ схемы, а не метаданных ORM.** Часть
  tenant-таблиц создана миграциями и модели не имеет (read-model'и), — в
  метаданных их нет вовсе, и построенный по ним порядок молча пропустил бы их
  зависимости. Схема в базе — единственный источник, который знает про все.
* **Цикл разрывается ТОЛЬКО обнулением nullable-FK, и разорванные связи
  перечисляются наружу.** Если в цикле не нашлось ни одной необязательной
  ссылки, разорвать его без потери данных нельзя — тогда операция отказывает с
  перечнем связей, а не «делает что может».
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "ForeignLink",
    "SchemaGraph",
    "UnbreakableCycleError",
    "reflect_schema_graph",
]


class UnbreakableCycleError(RuntimeError):
    """Цикл внешних ключей, который нечем разорвать без потери данных."""


@dataclass(frozen=True)
class ForeignLink:
    """Ссылка «дочерняя таблица → родительская» с признаком необязательности."""

    child: str
    parent: str
    columns: tuple[str, ...]
    nullable: bool

    def describe(self) -> str:
        return f"{self.child}.{'+'.join(self.columns)} → {self.parent}"


@dataclass(frozen=True)
class SchemaGraph:
    """Таблицы и связи между ними — то, что нужно и плану, и исполнению."""

    tables: tuple[str, ...]
    links: tuple[ForeignLink, ...]

    def parents_of(self, table: str) -> set[str]:
        return {link.parent for link in self.links if link.child == table}

    def retention_closure(self, seeds: Iterable[str]) -> dict[str, str]:
        """Кого ещё придётся сохранить, если сохраняем ``seeds``.

        Удерживаемая строка ссылается на родителя. Удалить родителя, оставив
        ребёнка, нельзя — внешний ключ не даст, а если бы дал, остались бы
        сироты. Поэтому срок хранения «протекает» вверх по ссылкам, и это должно
        быть видно в ПЛАНЕ: человек утверждает то, что произойдёт, а не то, что
        было бы при плоском прочтении реестра.
        """

        promoted: dict[str, str] = {}
        frontier = [table for table in seeds if table in self.tables]
        seen = set(frontier)
        while frontier:
            child = frontier.pop()
            for parent in sorted(self.parents_of(child)):
                if parent in seen:
                    continue
                seen.add(parent)
                promoted[parent] = child
                frontier.append(parent)
        return promoted

    def deletion_order(self, tables: Iterable[str]) -> tuple[list[str], list[ForeignLink]]:
        """Порядок удаления и связи, которые для этого пришлось разорвать.

        Возвращает таблицы так, что каждая удаляется раньше тех, на кого
        ссылается. Циклы разрываются обнулением необязательных ссылок; список
        разорванных связей возвращается наружу, чтобы попасть в акт: «мы
        обнулили эти поля» — часть ответа на вопрос, что именно было сделано.
        """

        subset = {table for table in tables if table in self.tables}
        deps: dict[str, set[str]] = {table: set() for table in subset}
        edges: dict[tuple[str, str], list[ForeignLink]] = {}
        for link in self.links:
            if link.child not in subset or link.parent not in subset:
                continue
            if link.child == link.parent:
                # Самоссылка не мешает: удаление всех строк таблицы одним
                # оператором проверяется по завершении оператора, а не построчно.
                continue
            deps[link.child].add(link.parent)
            edges.setdefault((link.child, link.parent), []).append(link)

        broken: list[ForeignLink] = []
        while True:
            cycles = [component for component in _strongly_connected(deps) if len(component) > 1]
            if not cycles:
                break
            for component in cycles:
                inner = sorted(key for key in edges if key[0] in component and key[1] in component)
                for key in inner:
                    links = edges[key]
                    if all(link.nullable for link in links):
                        broken.extend(links)
                        deps[key[0]].discard(key[1])
                        edges.pop(key)
                        break
                else:
                    raise UnbreakableCycleError(
                        "Цикл внешних ключей без единой необязательной ссылки: "
                        + ", ".join(sorted(component))
                    )

        # Таблицы без неудалённых зависимостей идут первыми — это «родители»;
        # удалять надо с конца, поэтому список разворачивается.
        pending = set(subset)
        parents_first: list[str] = []
        while pending:
            ready = sorted(table for table in pending if not (deps[table] & pending))
            if not ready:  # pragma: no cover - циклы уже разорваны выше
                raise UnbreakableCycleError(f"Неразрешимый порядок: {sorted(pending)}")
            parents_first.extend(ready)
            pending -= set(ready)
        return list(reversed(parents_first)), broken


def _strongly_connected(deps: dict[str, set[str]]) -> list[list[str]]:
    """Компоненты сильной связности (алгоритм Тарьяна, итеративный).

    Итеративный — потому что рекурсия на схеме в сотни таблиц упирается в лимит
    стека, и падение выглядело бы как «баг удаления», а не как переполнение.
    """

    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    result: list[list[str]] = []
    counter = 0

    for root in sorted(deps):
        if root in index:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, child_index = work[-1]
            if child_index == 0:
                index[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            children = sorted(deps.get(node, ()))
            if child_index < len(children):
                work[-1] = (node, child_index + 1)
                child = children[child_index]
                if child not in index:
                    work.append((child, 0))
                elif child in on_stack:
                    low[node] = min(low[node], index[child])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                result.append(sorted(component))
    return result


async def reflect_schema_graph(session: AsyncSession, tables: Iterable[str]) -> SchemaGraph:
    """Отразить живую схему: какие из ``tables`` есть в базе и как связаны."""

    wanted = {str(table) for table in tables}
    connection = await session.connection()

    def _reflect(sync_conn) -> SchemaGraph:  # noqa: ANN001 - sync bridge
        inspector = sa_inspect(sync_conn)
        present = sorted(wanted & set(inspector.get_table_names()))
        links: list[ForeignLink] = []
        for table in present:
            nullable = {
                column["name"]: bool(column.get("nullable", True))
                for column in inspector.get_columns(table)
            }
            for constraint in inspector.get_foreign_keys(table):
                parent = constraint.get("referred_table")
                columns = tuple(constraint.get("constrained_columns") or ())
                if not parent or not columns:
                    continue
                links.append(
                    ForeignLink(
                        child=table,
                        parent=parent,
                        columns=columns,
                        # Ссылка необязательна, только если КАЖДАЯ её колонка
                        # допускает NULL: составной ключ рвётся целиком.
                        nullable=all(nullable.get(column, False) for column in columns),
                    )
                )
        return SchemaGraph(tables=tuple(present), links=tuple(links))

    return await connection.run_sync(_reflect)
