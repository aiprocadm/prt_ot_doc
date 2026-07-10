"""Report execution engine: config → validated SQL → serialized rows.

Один и тот же компилятор обслуживает sync-preview (limit=PREVIEW_LIMIT) и
экспорт (limit=EXPORT_ROW_CAP в материализаторе). Фильтры / GROUP BY /
сортировка применяются на уровне SQL поверх subquery базового select'а
датасета — вычислимые колонки фильтруются наравне с физическими.
Enum-контракт (см. docstring datasets.py): фильтры коэрсируют входные строки
в Python enum-member'ы (col.enum_cls(value)) и сравнивают по типизированной
колонке; сериализация рендерит Enum → .value.
"""

from __future__ import annotations

import enum as _enum
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.report_builder.datasets import DATASETS, ColumnSpec, DatasetSpec

PREVIEW_LIMIT = 100
EXPORT_ROW_CAP = 50_000

__all__ = [
    "PREVIEW_LIMIT",
    "EXPORT_ROW_CAP",
    "ColumnMeta",
    "ReportConfigError",
    "ReportResult",
    "get_dataset",
    "run_report",
    "validate_config",
]


class ReportConfigError(Exception):
    """Невалидный config; на границе API маппится в 422."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ColumnMeta:
    key: str
    label: str
    kind: str


@dataclass(frozen=True)
class ReportResult:
    columns: list[ColumnMeta]
    rows: list[dict[str, Any]]
    total: int


def get_dataset(dataset_code: str) -> DatasetSpec:
    spec = DATASETS.get(dataset_code)
    if spec is None:
        raise ReportConfigError("dataset_unknown", f"Unknown dataset: {dataset_code}")
    return spec


def _require_column(spec: DatasetSpec, key: Any, *, context: str) -> ColumnSpec:
    if not isinstance(key, str) or spec.column(key) is None:
        raise ReportConfigError("column_unknown", f"Unknown column in {context}: {key}")
    return spec.column(key)  # type: ignore[return-value]


def _coerce_filter_value(col: ColumnSpec, op: str, value: Any) -> Any:
    if col.kind == "enum":
        assert col.enum_cls is not None
        try:
            if op == "in":
                if not isinstance(value, list) or not value:
                    raise ReportConfigError(
                        "filter_value_invalid", f"'in' expects a non-empty list for {col.key}"
                    )
                return [col.enum_cls(v) for v in value]
            return col.enum_cls(value)
        except ValueError as exc:
            raise ReportConfigError(
                "filter_value_invalid", f"Bad enum value for {col.key}: {value!r}"
            ) from exc
    if col.kind in {"date", "datetime"}:
        if not isinstance(value, str):
            raise ReportConfigError(
                "filter_value_invalid", f"ISO date string expected for {col.key}"
            )
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ReportConfigError(
                "filter_value_invalid", f"Bad date value for {col.key}: {value!r}"
            ) from exc
        if col.kind == "date":
            return parsed.date()
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    if col.kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ReportConfigError("filter_value_invalid", f"Number expected for {col.key}")
        return value
    if col.kind == "bool":
        if not isinstance(value, bool):
            raise ReportConfigError("filter_value_invalid", f"Boolean expected for {col.key}")
        return value
    if not isinstance(value, str):
        raise ReportConfigError("filter_value_invalid", f"String expected for {col.key}")
    return value


def _apply_filters(stmt, sq, spec: DatasetSpec, filters: list[Any]):
    for item in filters:
        if not isinstance(item, dict):
            raise ReportConfigError("filter_invalid", "Each filter must be an object")
        col = _require_column(spec, item.get("field"), context="filters")
        op = item.get("op")
        if op not in col.ops:
            raise ReportConfigError(
                "filter_op_invalid", f"Operator {op!r} is not allowed for {col.key} ({col.kind})"
            )
        value = _coerce_filter_value(col, op, item.get("value"))
        column = sq.c[col.key]
        if op == "eq":
            stmt = stmt.where(column == value)
        elif op == "neq":
            stmt = stmt.where(column != value)
        elif op == "contains":
            stmt = stmt.where(column.ilike(f"%{value}%"))
        elif op == "gte":
            stmt = stmt.where(column >= value)
        elif op == "lte":
            stmt = stmt.where(column <= value)
        elif op == "in":
            stmt = stmt.where(column.in_(value))
    return stmt


def _compile(spec: DatasetSpec, tenant_id: str, config: dict[str, Any] | None, now: datetime):
    cfg = config or {}
    filters = list(cfg.get("filters") or [])
    group_by = list(cfg.get("group_by") or [])
    aggregates = list(cfg.get("aggregates") or [])
    sort = list(cfg.get("sort") or [])
    sq = spec.build_stmt(tenant_id, now).subquery()

    out_meta: list[ColumnMeta] = []
    if group_by:
        group_cols = []
        for key in group_by:
            col = _require_column(spec, key, context="group_by")
            group_cols.append(sq.c[col.key])
            out_meta.append(ColumnMeta(key=col.key, label=col.label, kind=col.kind))
        if not aggregates:
            aggregates = [{"fn": "count"}]
        agg_exprs = []
        for agg in aggregates:
            fn = agg.get("fn") if isinstance(agg, dict) else None
            if fn == "count":
                agg_exprs.append(func.count().label("count"))
                out_meta.append(ColumnMeta(key="count", label="Количество", kind="number"))
            elif fn == "sum":
                col = _require_column(spec, agg.get("field"), context="aggregates")
                if not col.aggregatable:
                    raise ReportConfigError(
                        "aggregate_not_allowed", f"Column is not aggregatable: {col.key}"
                    )
                out_key = f"sum_{col.key}"
                agg_exprs.append(func.sum(sq.c[col.key]).label(out_key))
                out_meta.append(ColumnMeta(key=out_key, label=f"Сумма: {col.label}", kind="number"))
            else:
                raise ReportConfigError("aggregate_unknown", f"Unknown aggregate fn: {fn!r}")
        stmt = select(*group_cols, *agg_exprs)
        stmt = _apply_filters(stmt, sq, spec, filters)
        stmt = stmt.group_by(*group_cols)
    else:
        keys = list(cfg.get("columns") or []) or [c.key for c in spec.columns]
        sel_cols = []
        for key in keys:
            col = _require_column(spec, key, context="columns")
            sel_cols.append(sq.c[col.key])
            out_meta.append(ColumnMeta(key=col.key, label=col.label, kind=col.kind))
        stmt = select(*sel_cols)
        stmt = _apply_filters(stmt, sq, spec, filters)

    allowed = {m.key for m in out_meta}
    for item in sort:
        if not isinstance(item, dict):
            raise ReportConfigError("sort_invalid", "Each sort entry must be an object")
        key = item.get("field")
        direction = item.get("dir", "asc")
        if key not in allowed:
            raise ReportConfigError("sort_unknown", f"Unknown sort field: {key!r}")
        if direction not in {"asc", "desc"}:
            raise ReportConfigError("sort_dir_invalid", f"Bad sort direction: {direction!r}")
        stmt = stmt.order_by(asc(key) if direction == "asc" else desc(key))

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    return stmt, count_stmt, out_meta


def validate_config(dataset_code: str, config: dict[str, Any] | None) -> None:
    """Та же валидация, что и при исполнении, но без session/SQL — для
    create/update definition (битый config не должен сохраняться)."""
    spec = get_dataset(dataset_code)
    _compile(spec, "validation", config, datetime.now(tz=timezone.utc))


def _serialize_value(value: Any, kind: str) -> Any:
    if value is None:
        return None
    if isinstance(value, _enum.Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if kind == "bool":
        return bool(value)  # SQLite отдаёт 0/1 за case-выражения
    return value


async def run_report(
    session: AsyncSession,
    *,
    tenant_id: str,
    dataset_code: str,
    config: dict[str, Any] | None,
    limit: int,
    offset: int = 0,
) -> ReportResult:
    spec = get_dataset(dataset_code)
    now = datetime.now(tz=timezone.utc)
    stmt, count_stmt, out_meta = _compile(spec, tenant_id, config, now)
    total = int(await session.scalar(count_stmt) or 0)
    kind_by_key = {m.key: m.kind for m in out_meta}
    result = await session.execute(stmt.offset(offset).limit(limit))
    rows = [
        {k: _serialize_value(v, kind_by_key[k]) for k, v in dict(m).items()}
        for m in result.mappings().all()
    ]
    return ReportResult(columns=out_meta, rows=rows, total=total)
