"""BIZ-51 (Доп. №1 разд. 51): лента изменений у клиента и отчёты авто-аудита."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.ext.mutable import MutableDict
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

    # BIZ-51 срез-2 (разд. 51.2): откуда узнали об изменении. Специалисту это
    # видно неспроста — доверие к записи разное: «внёс коллега» и «увидели в
    # выгрузке 1С» проверяются по-разному, а без пометки лента выглядит так,
    # будто всё внесено руками.
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    #: На что ссылается источник: для импорта — id партии, для Data Quality —
    #: составная личность находки ``dq:<сущность>:<id>:<дата>`` (срез-3, cf03).
    #: Внешнего ключа нет намеренно: источников больше одного, и FK на «любую
    #: таблицу» не бывает — тот же довод, что у ``ImportRow``.
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)


class ClientAuditReport(TenantBaseModel):
    """Отчёт периодического авто-аудита по клиенту (BIZ-51 срез-7, разд. 51.3).

    ТЗ: «регулярная сверка с формированием отчёта: что изменилось, что
    просрочено, что нужно сделать». Отчёт — ЗАПИСЬ, а не пересчёт на лету:
    ценность аудита в том, что видно состояние НА ДАТУ и его динамику между
    неделями; пересчёт задним числом этого не даёт.
    """

    __tablename__ = "client_audit_report"
    __table_args__ = (
        # Отчёты читаются по клиенту, свежие сверху; и по этому же индексу
        # ищется «отчёт за период уже есть» при дедупликации тика.
        Index(
            "ix_client_audit_report_feed",
            "tenant_id",
            "managed_client_id",
            "period_end",
        ),
    )

    managed_client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("managed_client.id", ondelete="CASCADE"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    #: Итог светофора на дату отчёта (green/yellow/red/not_measured) —
    #: строкой, как в API: отдельный enum-тип в БД ради четырёх значений
    #: означал бы миграцию типа при каждом новом состоянии.
    overall: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Человеческий итог: «что изменилось, что просрочено, что нужно сделать».
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    #: Структура отчёта (направления, числа, действия) — для экрана и выгрузки.
    payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
