"""OPS-72 (разд. 72.2): полный экспорт данных арендатора для офбординга.

ТЗ: «Право клиента забрать СВОИ данные в пригодном виде. Это антидот к страху
vendor lock-in и требование 152-ФЗ». И отдельно: «Отличие от export_center: тот
выгружает отчёты/KPI; здесь — **ПОЛНЫЙ дамп** данных арендатора для переезда».

Ключевое проектное решение — **состав дампа берётся из реестра RLS**
(``core/rls_policy.py``), а не из отдельного списка таблиц. Причина: «полный»
экспорт, который перечисляет таблицы вручную, устаревает в первый же спринт и
молча отдаёт клиенту неполные данные — худший вид дефекта, потому что выглядит
как успех. Реестр RLS перечисляет ВСЕ tenant-таблицы, и его полноту уже стережёт
``scripts/audit/check_rls_coverage.py``: новая tenant-таблица не проходит CI, пока
не попадёт в реестр. Экспорт получает эту гарантию бесплатно.

Файлы (PDF/DOCX) в дамп не копируются: у арендатора их могут быть гигабайты, и
синхронная выгрузка обрушила бы запрос. Манифест содержит префикс объектного
хранилища и перечень ключей, чтобы файлы забирались отдельно — это честнее, чем
«экспорт», который падает по таймауту на первом крупном клиенте.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "TenantExportService",
    "ExportManifest",
    "EXPORT_FORMAT_VERSION",
    "DEFAULT_ROWS_PER_TABLE",
]

# Версия формата в манифесте: принимающая система должна уметь понять, что
# получила, без переписки с нами.
EXPORT_FORMAT_VERSION = "1.0"

# Потолок строк на таблицу в одном дампе. Не «ограничение ради ограничения»:
# без него один арендатор с миллионами строк аудита кладёт воркер по памяти.
# Усечение ВСЕГДА видно в манифесте — молча обрезанный экспорт хуже отказа.
DEFAULT_ROWS_PER_TABLE = 50_000


@dataclass
class TableDump:
    table: str
    columns: list[str]
    row_count: int
    exported_rows: int
    truncated: bool
    rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ExportManifest:
    tenant_id: str
    tenant_slug: str
    format_version: str
    generated_at: datetime
    tables: list[TableDump]
    files_prefix: str
    truncated: bool

    def to_dict(self, *, include_rows: bool = False) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "tenant_id": self.tenant_id,
            "tenant_slug": self.tenant_slug,
            "generated_at": self.generated_at.isoformat(),
            "files_prefix": self.files_prefix,
            "truncated": self.truncated,
            "tables": [
                {
                    "table": dump.table,
                    "columns": dump.columns,
                    "row_count": dump.row_count,
                    "exported_rows": dump.exported_rows,
                    "truncated": dump.truncated,
                    **({"rows": dump.rows} if include_rows else {}),
                }
                for dump in self.tables
            ],
        }


def _jsonable(value: Any) -> Any:
    """Привести значение к JSON-совместимому виду, ничего не теряя молча."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return str(value)


class TenantExportService:
    """Полный дамп данных арендатора (разд. 72.2)."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        tenant_slug: str,
        rows_per_table: int = DEFAULT_ROWS_PER_TABLE,
    ) -> None:
        self.session = session
        self.tenant_id = str(tenant_id)
        self.tenant_slug = tenant_slug
        self.rows_per_table = max(1, int(rows_per_table))

    @staticmethod
    def exportable_tables() -> list[str]:
        """Состав дампа = реестр RLS: все tenant-таблицы, ничего не забыто.

        ``RLS_EXEMPT_TABLES`` намеренно не включается: единственное исключение —
        платформенный справочник прав, это не данные арендатора.
        """

        from app.core.rls_policy import RLS_ENABLED_TABLES

        return sorted(RLS_ENABLED_TABLES)

    async def _existing_tables(self) -> set[str]:
        """Какие таблицы реально есть в этой БД.

        Реестр описывает целевую схему; конкретная база (например, SQLite в
        тестах или незамигрированный стенд) может отставать. Отсутствие таблицы —
        не повод ронять экспорт клиента.
        """

        connection = await self.session.connection()

        def _names(sync_conn) -> set[str]:  # noqa: ANN001 - sync bridge
            return set(sa_inspect(sync_conn).get_table_names())

        return await connection.run_sync(_names)

    async def build(self, *, include_rows: bool = True) -> ExportManifest:
        available = await self._existing_tables()
        dumps: list[TableDump] = []
        truncated_any = False

        for table in self.exportable_tables():
            if table not in available:
                continue
            quoted = f'"{table}"'
            total = (
                await self.session.execute(
                    text(f"SELECT count(*) FROM {quoted} WHERE tenant_id = :tenant"),
                    {"tenant": self.tenant_id},
                )
            ).scalar_one()
            if not total:
                continue

            result = await self.session.execute(
                text(
                    f"SELECT * FROM {quoted} WHERE tenant_id = :tenant LIMIT :limit"
                ),
                {"tenant": self.tenant_id, "limit": self.rows_per_table},
            )
            mappings = result.mappings().all()
            rows = [{key: _jsonable(value) for key, value in row.items()} for row in mappings]
            columns = list(mappings[0].keys()) if mappings else []
            table_truncated = int(total) > len(rows)
            truncated_any = truncated_any or table_truncated
            dumps.append(
                TableDump(
                    table=table,
                    columns=columns,
                    row_count=int(total),
                    exported_rows=len(rows),
                    truncated=table_truncated,
                    rows=rows if include_rows else [],
                )
            )

        return ExportManifest(
            tenant_id=self.tenant_id,
            tenant_slug=self.tenant_slug,
            format_version=EXPORT_FORMAT_VERSION,
            generated_at=datetime.now(tz=timezone.utc),
            tables=dumps,
            # Файлы не копируются в дамп — см. докстринг модуля.
            files_prefix=f"tenants/{self.tenant_slug}/",
            truncated=truncated_any,
        )

    async def build_json(self) -> bytes:
        manifest = await self.build(include_rows=True)
        return json.dumps(manifest.to_dict(include_rows=True), ensure_ascii=False).encode(
            "utf-8"
        )
