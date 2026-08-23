"""Пожарная безопасность — предметные модели дисциплины (Доп. №1 разд. 54.1).

Архитектурный принцип мультидисциплинарности (часть III ТЗ): общее ядро
(площадки, задачи, проверки, документы) НЕ дублируется — дисциплина добавляет
только своё. Первая собственная сущность контура ПБ — первичные средства
пожаротушения и системы противопожарной защиты: у них есть то, чего нет у
общих сущностей, — регламентные СРОКИ (перезарядка огнетушителя, поверка,
ТО систем АУПС/АУПТ/СОУЭ), и именно просрочки этих сроков — первое, что
смотрит инспектор МЧС.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SoftDeleteMixin, TenantBaseModel
from app.models.master_data import Site

#: Виды средств/систем защиты. VARCHAR, не PG-enum (снимает класс enum-parity,
#: прецедент cm01); канонический словарь — здесь, стережётся тестом среза.
FIRE_EQUIPMENT_KINDS: tuple[str, ...] = (
    "extinguisher",  # огнетушитель
    "hydrant",  # пожарный кран/гидрант
    "shield",  # пожарный щит
    "alarm_system",  # АУПС — сигнализация
    "suppression_system",  # АУПТ — пожаротушение
    "warning_system",  # СОУЭ — оповещение и эвакуация
)


class FireSafetyEquipment(TenantBaseModel, SoftDeleteMixin):
    """Единица учёта ПБ: огнетушитель, кран, щит или система защиты."""

    __tablename__ = "fire_safety_equipment"

    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    #: инвентарный/заводской номер или имя системы
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    #: помещение/место установки — свободный текст (реестра помещений в ядре нет)
    location: Mapped[str | None] = mapped_column(String(255))
    #: срок очередной перезарядки (огнетушители) — NULL, если не применимо
    recharge_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: срок очередной поверки/ТО (краны, системы) — NULL, если не применимо
    inspection_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )

    site: Mapped[Site | None] = relationship(backref="fire_safety_equipment")

    __table_args__ = (
        Index("ix_fire_equipment_tenant_kind", "tenant_id", "kind"),
    )
