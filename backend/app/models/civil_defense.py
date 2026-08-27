"""ГО и ЧС — предметные модели дисциплины (Доп. №1 разд. 56.1).

Архитектурный принцип мультидисциплинарности (преамбула разд. 54): общее ядро
(люди, площадки, документы, задачи, календарь) НЕ дублируется — дисциплина
добавляет только своё. Первая собственная сущность контура ГО и ЧС — реестр
нештатных формирований (НАСФ/НФГО) с составами.

ПОЧЕМУ СВОЯ СУЩНОСТЬ. До этого среза по разд. 56 не было НИ ОДНОЙ модели:
дисциплина ``Discipline.CIVIL_DEFENSE`` существовала словарной строкой,
числилась в «поимённый учёт не ведётся», весь контент сводился к комплекту
документов GOCHS_BASE, а библиотека правил прямо фиксировала причину: «ни
формирований, ни учений, ни планов — вешать правило не на что».

Состав формирования — люди из ЯДРА: строка состава ссылается на ``Person``,
а не заводит своих «бойцов».
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SoftDeleteMixin, TenantBaseModel
from app.models.master_data import Person

#: Виды нештатных формирований — ЗАКРЫТЫЙ словарь из двух (ФЗ-28 «О гражданской
#: обороне»): НАСФ создаются для аварийно-спасательных работ, НФГО — для
#: обеспечения выполнения мероприятий по ГО. Третьего вида не бывает.
#: НАЗНАЧЕНИЕ формирования (звено пожаротушения, пост РХН, санитарный пост…) —
#: свободная строка намеренно: профилей десятки, словарь в коде гарантированно
#: отстанет (довод перечня загрязняющих веществ из контура экологии).
CD_FORMATION_KINDS: dict[str, str] = {
    "nasf": "НАСФ (аварийно-спасательное формирование)",
    "nfgo": "НФГО (формирование по обеспечению ГО)",
}

#: Состояние строки состава — считается ПРИ ЧТЕНИИ по дате вывода.
CD_MEMBER_STATUS_TITLES: dict[str, str] = {
    "active": "В составе",
    "released": "Выведен из состава",
}


class CivilDefenseFormation(TenantBaseModel, SoftDeleteMixin):
    """Нештатное формирование: НАСФ или НФГО.

    ГРАНИЦА: платформа НЕ решает, обязана ли организация создавать
    формирования и сколько их нужно — это следует из категории организации по
    ГО и решений органа управления ГОЧС. Полей «требуется формирований» и
    «недоукомплектовано» здесь нет.
    """

    __tablename__ = "cd_formation"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    #: назначение — свободная строка (профилей десятки, см. словарь выше)
    purpose: Mapped[str | None] = mapped_column(String(255))
    #: командир — человек из ЯДРА, назначение необязательно
    commander_person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id"), nullable=True
    )
    #: оснащение первым срезом — заметкой; отдельный реестр оснащения, СИЗ ГО
    #: и средств оповещения — следующие срезы
    equipment_notes: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    commander: Mapped[Person | None] = relationship(foreign_keys=[commander_person_id])

    __table_args__ = (
        # Название уникально в организации: два «звена пожаротушения» без
        # уточнения — это ошибка ввода, а не два формирования.
        UniqueConstraint("tenant_id", "name", name="uq_cd_formation_name"),
    )


class CivilDefenseFormationMember(TenantBaseModel, SoftDeleteMixin):
    """Строка состава: человек из ядра в формировании.

    Вывод из состава — ДАТА, а не удаление строки: отчисленный остаётся в
    истории формирования, а в численности считаются только действующие.

    Одна строка на пару «формирование + человек»: повторное включение
    сбрасывает дату вывода, а не плодит дубли. Историю повторных входов
    первый срез не хранит — это осознанное упрощение, зафиксированное в
    handoff.
    """

    __tablename__ = "cd_formation_member"

    formation_id: Mapped[str] = mapped_column(
        ForeignKey("cd_formation.id"), nullable=False, index=True
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id"), nullable=False, index=True
    )
    #: роль в формировании (связной, санитар…) — свободная строка
    role_in_formation: Mapped[str | None] = mapped_column(String(128))
    assigned_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: дата вывода из состава; пусто — действующий
    released_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text)

    formation: Mapped[CivilDefenseFormation] = relationship(backref="members")
    person: Mapped[Person] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "formation_id", "person_id", name="uq_cd_member_person"
        ),
    )
