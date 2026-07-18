"""Report-builder saved definitions (P10-07 §24.3, slice rb01)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import SoftDeleteMixin, TenantBaseModel

__all__ = ["ReportDefinition"]


class ReportDefinition(TenantBaseModel, SoftDeleteMixin):
    """Сохранённый отчёт конструктора: датасет + config (фильтры/колонки/
    группировки/агрегаты/сортировка). ``is_system`` — «готовый шаблон» из ТЗ:
    неизменяемый (PATCH/DELETE → 400), на фронте только «Дублировать».
    Имя уникально per tenant БЕЗ фильтра deleted_at (паттерн ``PPESupplier``:
    soft-deleted тёзка честно даёт 409, слот не переиспользуется)."""

    __tablename__ = "report_definition"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    dataset_code: Mapped[str] = mapped_column(String(64), nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_report_definition_tenant_name"),
    )
