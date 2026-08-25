"""Экология — предметные модели дисциплины (Доп. №1 разд. 55).

Архитектурный принцип мультидисциплинарности (преамбула разд. 54): общее ядро
(площадки, люди, документы, договоры, задачи, календарь) НЕ дублируется —
дисциплина добавляет только своё. Первая собственная сущность контура экологии
— реестр объектов негативного воздействия на окружающую среду (НВОС).

ПОЧЕМУ СВОЯ СУЩНОСТЬ. До этого среза по экологии не было НИ ОДНОЙ модели:
дисциплина ``Discipline.ECOLOGY`` существовала только словарной строкой и
числилась в «поимённый учёт не ведётся», а весь экологический контент
сводился к комплекту документов ``ECO_WASTE``, где все значения вводятся
руками и никуда не сохраняются. Библиотека правил прямо фиксировала причину:
«в системе нет ни одного события экологии».

Объект НВОС не выражается полями площадки: у него свой номер в государственном
реестре, своя категория и свой жизненный цикл постановки на учёт и снятия с
него; на одной площадке может быть несколько таких объектов, а один объект
может охватывать несколько площадок.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SoftDeleteMixin, TenantBaseModel
from app.models.master_data import Site

#: Категории объектов НВОС — ЗАКРЫТЫЙ словарь (ФЗ-7 «Об охране окружающей
#: среды», ст. 4.2). От категории зависят и режим надзора, и состав
#: отчётности, поэтому величина обязана быть считаемой.
#:
#: ГРАНИЦА: категорию платформа НЕ ВЫЧИСЛЯЕТ. Она присваивается при постановке
#: на государственный учёт по критериям постановления Правительства (мощность,
#: виды воздействия, применяемые технологии), и этих данных в системе нет.
NVOS_CATEGORIES: dict[str, str] = {
    "I": "I категория — значительное негативное воздействие",
    "II": "II категория — умеренное негативное воздействие",
    "III": "III категория — незначительное негативное воздействие",
    "IV": "IV категория — минимальное негативное воздействие",
}

#: Состояние объекта в государственном реестре. Снятие с учёта НЕ удаляет
#: запись: история воздействия, отчётность и платежи остаются.
NVOS_STATUSES: dict[str, str] = {
    "registered": "На государственном учёте",
    "excluded": "Снят с учёта",
}


class EnvironmentalFacility(TenantBaseModel, SoftDeleteMixin):
    """Объект НВОС: постановка на учёт, категория, актуализация сведений."""

    __tablename__ = "nvos_facility"

    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: код объекта в государственном реестре объектов НВОС (формат
    #: 12-0177-001234-П) — без него объект не считается поставленным на учёт
    register_number: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(8), nullable=False)
    registered_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: дата последней АКТУАЛИЗАЦИИ сведений (разд. 55.1): сведения обновляют
    #: при изменении характеристик объекта, и специалисту важно видеть, когда
    #: это делали в последний раз
    actualized_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    excluded_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="registered", server_default="registered"
    )
    responsible: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

    site: Mapped[Site | None] = relationship(backref="nvos_facilities")

    __table_args__ = (
        # Один код реестра — один объект: дубль означает объект, заведённый
        # дважды, и любой счёт по категориям стал бы враньём.
        UniqueConstraint("tenant_id", "register_number", name="uq_nvos_facility_register"),
        Index("ix_nvos_facility_tenant_category", "tenant_id", "category"),
    )
