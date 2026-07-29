"""OPS-72 (разд. 72.3): жизненный цикл офбординга арендатора.

ТЗ: «После ухода — управляемое удаление, а не "данные висят вечно" или "удалили
сразу и потеряли"». Стадии из карты состояний разд. 72.1, которых в продукте не
было: **офбординг** и **пост-офбординг**.

Запись живёт от заявки на расторжение до окончательного удаления и остаётся после
него: акт об удалении — это ответ на вопрос «а что именно вы стёрли и когда»,
и он нужен ровно тогда, когда самих данных уже нет.

Таблица tenant-scoped, поэтому армируется RLS (SEC-65): арендатор видит СВОЙ
статус офбординга, а управляющий тенант работает через bypass-сессию флота — тот
же приём, что в ``api/routes/platform_tenants.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import TenantBaseModel

__all__ = ["TenantOffboarding", "OFFBOARDING_STATUSES"]

OFFBOARDING_STATUSES: tuple[str, ...] = (
    # Заявка подана, идёт grace-период: данные доступны только на чтение, клиент
    # может вернуться или забрать выгрузку.
    "grace",
    # Grace истёк, план удаления утверждён и исполнен — есть акт.
    "purged",
    # Клиент вернулся или расторжение отменено.
    "cancelled",
)


class TenantOffboarding(TenantBaseModel):
    """Заявка на офбординг и её исход."""

    __tablename__ = "tenant_offboarding"
    __table_args__ = (Index("ix_tenant_offboarding_tenant_status", "tenant_id", "status"),)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="grace")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Сколько дней данные ещё живут после заявки. Разд. 72.3: «на случай возврата
    # или споров — конфигурируемо».
    grace_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    grace_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Акт об удалении: что удалено, что сохранено обезличенным и на каком
    # основании. Хранится ПОСЛЕ удаления — именно тогда он и нужен.
    purge_act: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )

    requested_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    requested_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
