"""Промышленная безопасность — предметные модели дисциплины (Доп. №1 разд. 54.2).

Архитектурный принцип мультидисциплинарности (преамбула разд. 54): общее ядро
(площадки, люди, документы, проверки, задачи) НЕ дублируется — дисциплина
добавляет только своё. Первая собственная сущность контура ПромБеза — реестр
опасных производственных объектов (ОПО).

ПОЧЕМУ РЕЕСТР, А НЕ ПОЛЯ ПЛОЩАДКИ. До этого среза «ОПО» выражалось тремя
полями у ``Site``: булевым признаком, номером строкой и ``hazard_class`` —
свободной строкой на 32 знака. Два следствия, оба ломающие требование ТЗ
«идентификация, класс опасности, регистрационные сведения»:

1. **Свободная строка класса перегружена двумя смыслами.** В неё кладут и
   класс опасности ОПО («II»), и категорию пожарной опасности помещения
   («В2»). Вопрос «сколько у нас объектов I класса» не имел ответа.
2. **ОПО и площадка — не одно и то же.** На одной площадке бывает несколько
   зарегистрированных объектов (сеть газопотребления, склад ГСМ, подъёмные
   сооружения), у каждого свой регистрационный номер и свой класс опасности.
   Полями площадки этого не выразить в принципе.

``Site.hazard_class`` этот срез НЕ трогает: там лежат живые данные двух разных
смыслов, разбор которых — отдельное решение, а не побочный эффект.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SoftDeleteMixin, TenantBaseModel
from app.models.master_data import Site

#: Классы опасности ОПО — ЗАКРЫТЫЙ словарь (ФЗ-116 «О промышленной
#: безопасности опасных производственных объектов», приложение 2). Ровно
#: четыре значения, римскими цифрами, как в свидетельстве о регистрации.
#: Именно от класса зависит режим надзора, поэтому величина обязана быть
#: считаемой, а не пересказываемой.
OPO_HAZARD_CLASSES: dict[str, str] = {
    "I": "I класс — чрезвычайно высокая опасность",
    "II": "II класс — высокая опасность",
    "III": "III класс — средняя опасность",
    "IV": "IV класс — низкая опасность",
}

#: Состояние объекта в государственном реестре. Исключение из реестра НЕ
#: удаляет запись: история эксплуатации и связанные документы остаются.
OPO_STATUSES: dict[str, str] = {
    "registered": "Зарегистрирован",
    "excluded": "Исключён из реестра",
}


class HazardousFacility(TenantBaseModel, SoftDeleteMixin):
    """Опасный производственный объект: идентификация и регистрационные сведения."""

    __tablename__ = "hazardous_facility"

    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id"), nullable=True, index=True
    )
    #: наименование как в свидетельстве о регистрации
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: регистрационный номер в госреестре (формат А01-12345-0001) — без него
    #: объекта в реестре не существует, это его удостоверение
    register_number: Mapped[str] = mapped_column(String(64), nullable=False)
    hazard_class: Mapped[str] = mapped_column(String(8), nullable=False)
    registered_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    excluded_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="registered", server_default="registered"
    )
    #: ответственный за производственный контроль на объекте
    responsible: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

    site: Mapped[Site | None] = relationship(backref="hazardous_facilities")

    __table_args__ = (
        # Один госномер — один объект. Дубль означает, что объект завели
        # дважды, и любой счёт по классам стал бы враньём.
        UniqueConstraint(
            "tenant_id", "register_number", name="uq_hazardous_facility_register"
        ),
        Index("ix_hazardous_facility_tenant_class", "tenant_id", "hazard_class"),
    )
