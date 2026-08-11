"""OPS-72: где у арендатора лежат ключи файлов.

Один источник правды для двух операций, которые обязаны видеть ОДИН И ТОТ ЖЕ
набор файлов: выгрузка архивом (разд. 72.2) и удаление (разд. 72.3). Если бы
списки разошлись, клиент получил бы в архиве меньше, чем у него стёрли, —
и узнал бы об этом у нового поставщика.

Колонки ищутся **по суффиксу имени в живой схеме**, а не по списку таблиц:
новая таблица с вложением появится раньше, чем кто-нибудь вспомнит про такой
список, и её файлы молча остались бы жить после «полного удаления» (или не
попали бы в «полный» архив).
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["FILE_KEY_COLUMN_SUFFIXES", "file_key_columns", "collect_file_keys"]

FILE_KEY_COLUMN_SUFFIXES: tuple[str, ...] = ("storage_key", "file_key")


async def file_key_columns(session: AsyncSession, tables: Iterable[str]) -> dict[str, list[str]]:
    """Таблица → колонки с ключами хранилища (только реально существующие)."""

    wanted = list(dict.fromkeys(str(table) for table in tables))
    connection = await session.connection()

    def _columns(sync_conn) -> dict[str, list[str]]:  # noqa: ANN001 - sync bridge
        inspector = sa_inspect(sync_conn)
        present = set(inspector.get_table_names())
        found: dict[str, list[str]] = {}
        for table in wanted:
            if table not in present:
                continue
            names = [
                column["name"]
                for column in inspector.get_columns(table)
                if column["name"].endswith(FILE_KEY_COLUMN_SUFFIXES)
            ]
            if names:
                found[table] = names
        return found

    return await connection.run_sync(_columns)


async def collect_file_keys(
    session: AsyncSession, tables: Iterable[str], *, tenant_id: str
) -> list[str]:
    """Все ключи файлов арендатора в перечисленных таблицах, без повторов."""

    columns_by_table = await file_key_columns(session, tables)
    keys: list[str] = []
    for table, columns in sorted(columns_by_table.items()):
        for column in columns:
            rows = await session.execute(
                text(
                    f'SELECT DISTINCT "{column}" FROM "{table}" '
                    f'WHERE tenant_id = :tenant AND "{column}" IS NOT NULL'
                ),
                {"tenant": str(tenant_id)},
            )
            keys.extend(str(value) for (value,) in rows.all() if value)
    return sorted(set(keys))
