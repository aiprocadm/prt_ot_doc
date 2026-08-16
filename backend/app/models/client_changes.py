"""BIZ-51 срез-1 (Доп. №1 разд. 51.1): лента изменений у клиента."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domains.managed_clients.change_feed import ChangeStatus, ClientChangeKind
from app.models.base import SoftDeleteMixin, TenantBaseModel, native_enum


class ClientChange(TenantBaseModel, SoftDeleteMixin):
    """Одно зафиксированное изменение у обслуживаемого клиента."""

    __tablename__ = "client_change"
    __table_args__ = (
        # Лента всегда читается по клиенту и в обратном хронологическом
        # порядке: без этого индекса каждый показ ленты перебирал бы все
        # изменения всех клиентов аутсорсера.
        Index("ix_client_change_feed", "tenant_id", "managed_client_id", "happened_on"),
    )

    managed_client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("managed_client.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[ClientChangeKind] = mapped_column(
        native_enum(ClientChangeKind, name="clientchangekind"), nullable=False
    )
    #: Дата САМОГО изменения, а не записи о нём: сотрудника приняли в пятницу,
    #: а специалист внёс это в понедельник — сроки считаются от пятницы.
    happened_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: Что именно изменилось, словами специалиста: «принят слесарь Иванов».
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[ChangeStatus] = mapped_column(
        native_enum(ChangeStatus, name="clientchangestatus"),
        nullable=False,
        default=ChangeStatus.NEW,
    )
    #: Кто и когда разобрал. Без этого «разобрано» не отвечает на вопрос «кем»,
    #: а в сопровождении это первый вопрос при разборе жалобы клиента.
    handled_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
