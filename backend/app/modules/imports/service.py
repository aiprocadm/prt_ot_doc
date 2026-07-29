"""OPS-71 (разд. 71.1): применение плана импорта к БД и откат партии.

Три операции: сухой прогон (ничего не пишет), применение (пишет корректные строки,
ошибочные откладывает) и откат партии целиком.

**Применение заново разбирает файл и заново строит план** — клиентский предпросмотр
не является входными данными. Между предпросмотром и применением проходят минуты,
за которые справочник мог измениться, а доверять присланному «я уже посчитал» —
значит позволить записать в БД что угодно. Тот же приём в ``services/sout_import.py``.
"""

from __future__ import annotations

import enum as py_enum
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.imports import ImportBatch, ImportRow
from app.models.master_data import Company, Position
from app.models.tenanting import Tenant
from app.modules.imports.parsers import ParsedFile, parse_import_file
from app.modules.imports.planner import (
    KEY_SEPARATOR,
    ImportPlan,
    MappingResult,
    build_mapping,
    build_plan,
    make_key,
    normalize_header,
    resolve_rows,
)
from app.modules.imports.registry import ImportTarget, get_target

__all__ = [
    "ImportMappingError",
    "ImportRollbackError",
    "ImportService",
]


class ImportMappingError(Exception):
    """Обязательная колонка не найдена — файл отвергается целиком (до записи).

    Построчная ошибка здесь была бы бесполезна: она повторилась бы на каждой из
    тысячи строк и утопила бы настоящие проблемы данных.
    """

    def __init__(self, missing: list[str], headers: list[str]):
        self.missing = missing
        self.headers = headers
        super().__init__("Missing required columns: " + ", ".join(missing))


class ImportRollbackError(Exception):
    """Откат невозможен целиком — не делаем его частично."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, py_enum.Enum):
        return value.value
    return value


def _normalize_current(value: Any) -> Any:
    """Значение из БД → тот же вид, в котором его отдаёт планировщик."""

    if isinstance(value, py_enum.Enum):
        return value.value
    if isinstance(value, datetime):
        return value.date()
    return value


class ImportService:
    """Импорт поверх реестра целей. Не знает ни одной сущности поимённо."""

    def __init__(self, session: AsyncSession, tenant: Tenant):
        self.session = session
        self.tenant = tenant

    # --- справочники -------------------------------------------------------

    async def load_lookups(self, target: ImportTarget) -> dict[str, dict[str, str]]:
        needed = {c.lookup for c in target.columns if c.lookup}
        lookups: dict[str, dict[str, str]] = {}

        if "company" in needed:
            rows = (
                await self.session.execute(
                    select(Company.id, Company.name).where(
                        Company.tenant_id == self.tenant.id,
                        Company.deleted_at.is_(None),
                    )
                )
            ).all()
            lookups["company"] = {normalize_header(name): cid for cid, name in rows}

        if "position" in needed:
            rows = (
                await self.session.execute(
                    select(Position.id, Position.company_id, Position.name).where(
                        Position.tenant_id == self.tenant.id,
                        Position.deleted_at.is_(None),
                    )
                )
            ).all()
            lookups["position"] = {
                f"{company_id}{KEY_SEPARATOR}{normalize_header(name)}": pid
                for pid, company_id, name in rows
            }

        return lookups

    # --- существующие записи ----------------------------------------------

    def _tracked_fields(self, target: ImportTarget) -> list[str]:
        fields = [c.field for c in target.columns]
        fields += [c.also_set_raw for c in target.columns if c.also_set_raw]
        return fields

    async def _load_existing(
        self, target: ImportTarget, resolved_values: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Найти записи, уже соответствующие ключам строк файла.

        Выборка сужается значениями ИЗ ФАЙЛА по каждому компоненту ключа, а не
        «загрузим всех сотрудников арендатора»: у клиента, ради которого этот
        импорт и делается, их десятки тысяч.
        """

        model = target.model
        conditions_sets = []
        for natural in target.natural_keys:
            values_by_field: dict[str, set[Any]] = {}
            for values in resolved_values:
                if all(values.get(f) not in (None, "") for f in natural.fields):
                    for f in natural.fields:
                        values_by_field.setdefault(f, set()).add(values[f])
            if values_by_field:
                conditions_sets.append(values_by_field)

        if not conditions_sets:
            return {}

        found: dict[str, dict[str, Any]] = {}
        tracked = self._tracked_fields(target)
        has_soft_delete = hasattr(model, "deleted_at")

        for values_by_field in conditions_sets:
            stmt = select(model).where(model.tenant_id == self.tenant.id)
            if has_soft_delete:
                stmt = stmt.where(model.deleted_at.is_(None))
            for field_name, values in values_by_field.items():
                stmt = stmt.where(getattr(model, field_name).in_(list(values)))
            for entity in (await self.session.execute(stmt)).scalars().all():
                snapshot = {"id": entity.id}
                for field_name in tracked:
                    if hasattr(entity, field_name):
                        snapshot[field_name] = _normalize_current(getattr(entity, field_name))
                # Запись индексируется по КАЖДОМУ варианту ключа, который она
                # удовлетворяет: файл может опознать её по табельному номеру, а
                # соседняя строка — по ФИО.
                for natural in target.natural_keys:
                    if all(snapshot.get(f) not in (None, "") for f in natural.fields):
                        key = f"{natural.title}{KEY_SEPARATOR}" + make_key(natural.fields, snapshot)
                        found[key] = snapshot
        return found

    # --- построение плана --------------------------------------------------

    async def build(
        self,
        target: ImportTarget,
        filename: str,
        content: bytes,
        overrides: dict[str, str] | None = None,
    ) -> tuple[ImportPlan, MappingResult, ParsedFile]:
        parsed = parse_import_file(filename, content)
        mapping = build_mapping(target, parsed.headers, overrides)
        if mapping.missing_required:
            raise ImportMappingError(mapping.missing_required, parsed.headers)

        lookups = await self.load_lookups(target)
        resolved, unknown = resolve_rows(target, parsed, mapping.mapping, lookups)
        existing = await self._load_existing(target, [r.values for r in resolved if r.ok])
        plan = build_plan(
            target,
            resolved,
            existing,
            mapping.mapping,
            mapping.unmapped_headers,
            unknown,
        )
        return plan, mapping, parsed

    # --- применение --------------------------------------------------------

    def _coerce_for_model(self, target: ImportTarget, field_name: str, value: Any) -> Any:
        """Строка плана → значение, которое примет колонка модели."""

        column = sa_inspect(target.model).columns.get(field_name)
        if column is None or value is None:
            return value
        if isinstance(column.type, SAEnum) and column.type.enum_class:
            return column.type.enum_class(value)
        if isinstance(value, str):
            # Даты в снимке отката лежат строками (JSON не знает date) —
            # вернуть их типом, иначе SQLite примет строку, а PostgreSQL нет.
            try:
                python_type = column.type.python_type
            except NotImplementedError:  # pragma: no cover — JSON и подобные
                return value
            if python_type is date:
                return date.fromisoformat(value)
            if python_type is datetime:
                return datetime.fromisoformat(value)
        return value

    async def apply(
        self,
        target: ImportTarget,
        filename: str,
        content: bytes,
        *,
        overrides: dict[str, str] | None = None,
        actor_id: str | None = None,
    ) -> tuple[ImportBatch, ImportPlan]:
        plan, mapping, _ = await self.build(target, filename, content, overrides)

        batch = ImportBatch(
            tenant_id=self.tenant.id,
            target=target.code,
            status="applied",
            source_filename=filename[:255],
            source_format=filename.rsplit(".", 1)[-1].lower()[:16],
            mapping=dict(plan.mapping),
            notes={
                "unmapped_headers": list(plan.unmapped_headers),
                "unknown_references": {k: list(v) for k, v in plan.unknown_references.items()},
                "ambiguous_headers": list(mapping.ambiguous_headers),
            },
            applied_by=actor_id,
            applied_at=_now(),
        )
        self.session.add(batch)
        await self.session.flush()

        table = target.model.__tablename__
        counts = {"created": 0, "updated": 0, "skipped": 0, "failed": 0}

        for planned in plan.rows:
            if planned.action == "error":
                counts["failed"] += 1
                self.session.add(
                    ImportRow(
                        tenant_id=self.tenant.id,
                        batch_id=batch.id,
                        row_number=planned.row_number,
                        action="failed",
                        natural_key=(planned.natural_key or None),
                        errors=[
                            {"code": e.code, "field": e.field, "message": e.message}
                            for e in planned.errors
                        ],
                        message="; ".join(e.message for e in planned.errors)[:2000],
                    )
                )
                continue

            if planned.action == "skip":
                counts["skipped"] += 1
                self.session.add(
                    ImportRow(
                        tenant_id=self.tenant.id,
                        batch_id=batch.id,
                        row_number=planned.row_number,
                        action="skipped",
                        natural_key=planned.natural_key,
                        entity_table=table,
                        entity_id=planned.entity_id,
                    )
                )
                continue

            if planned.action == "create":
                entity = target.model(
                    tenant_id=self.tenant.id,
                    **{f: self._coerce_for_model(target, f, v) for f, v in planned.values.items()},
                )
                # SAVEPOINT на строку: ограничение БД, которое планировщик увидеть не
                # мог (например, уникальность, занятая МЯГКО удалённой записью),
                # обязано провалить ОДНУ строку. Без изоляции такой INSERT рвёт всю
                # транзакцию, и «частичный импорт» из разд. 71.1 превращается в 500
                # на весь файл — ровно то поведение, которого требование избегает.
                try:
                    async with self.session.begin_nested():
                        self.session.add(entity)
                        await self.session.flush()
                except IntegrityError as exc:
                    counts["failed"] += 1
                    self.session.add(
                        ImportRow(
                            tenant_id=self.tenant.id,
                            batch_id=batch.id,
                            row_number=planned.row_number,
                            action="failed",
                            natural_key=planned.natural_key,
                            errors=[
                                {
                                    "code": "constraint_violation",
                                    "field": None,
                                    "message": "Database rejected the row "
                                    f"({type(exc.orig).__name__ if exc.orig else 'IntegrityError'})",
                                }
                            ],
                        )
                    )
                    continue
                counts["created"] += 1
                self.session.add(
                    ImportRow(
                        tenant_id=self.tenant.id,
                        batch_id=batch.id,
                        row_number=planned.row_number,
                        action="created",
                        natural_key=planned.natural_key,
                        entity_table=table,
                        entity_id=entity.id,
                    )
                )
                continue

            # update
            entity = await self.session.get(target.model, planned.entity_id)
            if entity is None or getattr(entity, "tenant_id", None) != self.tenant.id:
                counts["failed"] += 1
                self.session.add(
                    ImportRow(
                        tenant_id=self.tenant.id,
                        batch_id=batch.id,
                        row_number=planned.row_number,
                        action="failed",
                        natural_key=planned.natural_key,
                        errors=[
                            {
                                "code": "entity_vanished",
                                "field": None,
                                "message": "Row disappeared between planning and apply",
                            }
                        ],
                    )
                )
                continue
            try:
                async with self.session.begin_nested():
                    for field_name, value in planned.values.items():
                        setattr(
                            entity, field_name, self._coerce_for_model(target, field_name, value)
                        )
                    await self.session.flush()
            except IntegrityError:
                counts["failed"] += 1
                self.session.add(
                    ImportRow(
                        tenant_id=self.tenant.id,
                        batch_id=batch.id,
                        row_number=planned.row_number,
                        action="failed",
                        natural_key=planned.natural_key,
                        errors=[
                            {
                                "code": "constraint_violation",
                                "field": None,
                                "message": "Database rejected the update",
                            }
                        ],
                    )
                )
                continue
            counts["updated"] += 1
            self.session.add(
                ImportRow(
                    tenant_id=self.tenant.id,
                    batch_id=batch.id,
                    row_number=planned.row_number,
                    action="updated",
                    natural_key=planned.natural_key,
                    entity_table=table,
                    entity_id=entity.id,
                    before_values={f: _json_safe(v) for f, v in planned.before.items()},
                )
            )

        batch.total_rows = len(plan.rows)
        batch.created_count = counts["created"]
        batch.updated_count = counts["updated"]
        batch.skipped_count = counts["skipped"]
        batch.failed_count = counts["failed"]
        await self.session.flush()
        return batch, plan

    # --- откат -------------------------------------------------------------

    async def get_batch(self, batch_id: str) -> ImportBatch | None:
        batch = await self.session.get(ImportBatch, batch_id)
        if batch is None or batch.tenant_id != self.tenant.id:
            return None
        return batch

    async def list_rows(self, batch_id: str, action: str | None = None) -> list[ImportRow]:
        stmt = select(ImportRow).where(
            ImportRow.tenant_id == self.tenant.id, ImportRow.batch_id == batch_id
        )
        if action:
            stmt = stmt.where(ImportRow.action == action)
        stmt = stmt.order_by(ImportRow.row_number)
        return list((await self.session.execute(stmt)).scalars().all())

    async def rollback(self, batch: ImportBatch, *, actor_id: str | None = None) -> ImportBatch:
        if batch.status == "rolled_back":
            raise ImportRollbackError(
                "import_batch_already_rolled_back", "Batch has already been rolled back"
            )

        target = get_target(batch.target)
        if target is None:
            raise ImportRollbackError(
                "import_target_unknown",
                f"Target {batch.target!r} is no longer registered, cannot roll back safely",
            )

        rows = await self.list_rows(batch.id)

        # Сначала откатываем обновления, потом удаляем созданное: обновлённая
        # запись может ссылаться на созданную, и обратный порядок упёрся бы в
        # собственный внешний ключ партии.
        for row in rows:
            if row.action != "updated" or not row.entity_id:
                continue
            entity = await self.session.get(target.model, row.entity_id)
            if entity is None:
                continue
            for field_name, value in (row.before_values or {}).items():
                setattr(entity, field_name, self._coerce_for_model(target, field_name, value))

        for row in rows:
            if row.action != "created" or not row.entity_id:
                continue
            entity = await self.session.get(target.model, row.entity_id)
            if entity is None:
                continue
            await self.session.delete(entity)
            try:
                await self.session.flush()
            except IntegrityError as exc:
                # На созданную импортом запись уже сослались. Удалить её «как
                # получится» значило бы порвать чужие данные, а откатить половину
                # партии — оставить состояние, которого не было никогда.
                raise ImportRollbackError(
                    "import_rollback_blocked",
                    f"Row {row.row_number}: imported record is referenced by other data "
                    "and cannot be removed. Roll back the dependent data first.",
                ) from exc

        batch.status = "rolled_back"
        batch.rolled_back_at = _now()
        batch.rolled_back_by = actor_id
        await self.session.flush()
        return batch
