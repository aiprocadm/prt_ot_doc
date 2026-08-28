"""БДД — предметные модели дисциплины (Доп. №1 разд. 56.2).

Архитектурный принцип мультидисциплинарности (преамбула разд. 54): общее ядро
(люди, площадки, документы, задачи, календарь) НЕ дублируется — дисциплина
добавляет только своё. Первая собственная сущность контура БДД — реестр
транспортных средств.

ПОЧЕМУ СВОЯ СУЩНОСТЬ. До этого среза по разд. 56.2 не было НИ ОДНОЙ модели
транспорта: ТЗ отсылает к «transport safety (vNext §17.3)», но в коде есть
только словарная строка дисциплины, комплект документов BDD_BASE и запись в
библиотеке правил. Ни ТС, ни водителей, ни путевых листов.

Водители, путевые листы, предрейсовые осмотры и учёт ДТП — следующие срезы:
все они ссылаются на транспортное средство, которого до сих пор не
существовало.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SoftDeleteMixin, TenantBaseModel
from app.models.master_data import Site

#: Виды транспортных средств — ЗАКРЫТЫЙ словарь. Деление нужно для БДД: у
#: автобуса, грузовика и спецтехники разный порядок контроля и разные
#: требования к водителю. Марка и модель остаются свободной строкой — их
#: тысячи, и словарь в коде гарантированно отстанет.
VEHICLE_KINDS: dict[str, str] = {
    "passenger_car": "Легковой автомобиль",
    "truck": "Грузовой автомобиль",
    "bus": "Автобус",
    "special": "Спецтехника",
    "trailer": "Прицеп / полуприцеп",
}

#: Состояние ТС в парке — ЗАКРЫТЫЙ словарь. Списание меняет СОСТОЯНИЕ, а не
#: удаляет запись: машина остаётся в истории парка. Просрочки считаются только
#: по эксплуатируемым — у списанной машины просроченный полис это шум, а не
#: проблема.
VEHICLE_STATUSES: dict[str, str] = {
    "in_service": "В эксплуатации",
    "suspended": "Не эксплуатируется",
    "decommissioned": "Списано",
}

#: Состояние срока документа ТС.
#:
#: ОТЛИЧИЕ ОТ ДОКУМЕНТОВ ПБ И ГО, где пустой срок означал БЕССРОЧНО: у
#: диагностической карты и полиса ОСАГО бессрочности НЕ БЫВАЕТ. Пустая дата
#: значит только, что сведений нет — и это НЕ то же самое, что «просрочено»:
#: «мы не знаем» и «истекло» — разные утверждения.
VEHICLE_DOC_STATUS_TITLES: dict[str, str] = {
    "missing": "Сведения не внесены",
    "ok": "Действует",
    "due_soon": "Скоро истекает",
    "overdue": "Просрочено",
}

#: Состояние тахографа. «Не установлен» — ОТДЕЛЬНОЕ значение: отсутствие
#: прибора и отсутствие сведений о его поверке это разные факты.
#:
#: ГРАНИЦА: платформа НЕ решает, нужен ли тахограф на этой машине — это
#: следует из вида перевозок, массы и категории ТС по закону.
TACHOGRAPH_STATUS_TITLES: dict[str, str] = {
    "not_installed": "Не установлен",
    **VEHICLE_DOC_STATUS_TITLES,
}


class Vehicle(TenantBaseModel, SoftDeleteMixin):
    """Транспортное средство парка: учёт, сроки документов, тахограф.

    ГРАНИЦА: платформа НЕ решает, нужен ли тахограф, требуется ли лицензия и
    какой срок у диагностической карты. Это следует из вида перевозок, массы и
    категории ТС по закону, а таких данных в системе нет — храним внесённое.
    """

    __tablename__ = "road_vehicle"

    #: государственный регистрационный знак — уникален у арендатора:
    #: одна машина это одна запись, второй такой же номер — ошибка ввода
    plate_number: Mapped[str] = mapped_column(String(32), nullable=False)
    brand_model: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="in_service")
    vin: Mapped[str | None] = mapped_column(String(32))
    year_made: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: площадка приписки; ТС может быть общим для организации
    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id"), nullable=True, index=True
    )
    #: диагностическая карта действительна до; пусто — СВЕДЕНИЙ НЕТ
    inspection_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: полис ОСАГО действителен до; пусто — СВЕДЕНИЙ НЕТ
    insurance_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: реквизиты лицензии/разрешения на перевозки — свободная строка:
    #: платформа не решает, требуется ли лицензия
    license_number: Mapped[str | None] = mapped_column(String(128))
    license_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    tachograph_installed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    #: поверка блока СКЗИ тахографа до
    tachograph_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text)

    site: Mapped[Site | None] = relationship(backref="vehicles")

    __table_args__ = (
        UniqueConstraint("tenant_id", "plate_number", name="uq_vehicle_plate"),
        Index("ix_vehicle_tenant_status", "tenant_id", "status"),
    )
