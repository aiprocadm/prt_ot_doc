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

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SoftDeleteMixin, TenantBaseModel
from app.models.master_data import Person, Site

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


#: Виды учений и тренировок ГО — ЗАКРЫТЫЙ словарь. Деление установлено
#: положением о подготовке населения в области ГО: у каждого вида свои
#: участники, продолжительность и порядок. Это НЕ то же, что тренировки ПБ
#: (там эвакуация и первичные средства) — основания и органы разные.
CD_DRILL_KINDS: dict[str, str] = {
    "command_staff": "Командно-штабное учение",
    "tactical_special": "Тактико-специальное учение",
    "complex": "Комплексное учение",
    "facility_training": "Объектовая тренировка",
}

#: Результат проведённого учения — закрытый словарь: «анализ» это сравнимая
#: оценка, а не пересказ своими словами (пересказ живёт в findings).
#: Словарь намеренно совпадает с оценками тренировок ПБ: одинаковый смысл —
#: одинаковые слова, иначе два экрана продукта судят об одном по-разному.
CD_DRILL_OUTCOMES: dict[str, str] = {
    "passed": "Проведено, задачи выполнены",
    "with_remarks": "Проведено с замечаниями",
    "failed": "Задачи не выполнены",
}

#: Состояние учения — считается ПРИ ЧТЕНИИ по датам.
CD_DRILL_STATUS_TITLES: dict[str, str] = {
    "planned": "Запланировано",
    "held": "Проведено",
    "overdue": "Просрочено",
}


class CivilDefenseDrill(TenantBaseModel, SoftDeleteMixin):
    """Учение или тренировка ГО: план-график, протокол, анализ.

    СВОЯ таблица, а не переиспользование тренировок ПБ: у учения ГО есть то,
    чего у пожарной тренировки не бывает — задействованное ФОРМИРОВАНИЕ
    (срез-1). И виды разные: командно-штабное учение и тренировка по эвакуации
    отличаются основанием, участниками и органом, который их требует.

    Формирование НЕОБЯЗАТЕЛЬНО: объектовая тренировка проводится всем
    персоналом, а не силами звена — требовать привязку значило бы выдумывать
    связь, которой нет.

    ГРАНИЦА: платформа НЕ назначает периодичность учений — она установлена
    постановлением Правительства и зависит от категории организации по ГО.
    """

    __tablename__ = "cd_drill"

    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    #: план-график: дата, на которую учение назначено (обязательна — учение
    #: рождается ЗАПЛАНИРОВАННЫМ, иначе плана-графика нет)
    planned_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: протокол: дата фактического проведения; NULL — ещё не проводилось
    held_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: задействованное формирование (срез-1); NULL — учение общеобъектовое
    formation_id: Mapped[str | None] = mapped_column(
        ForeignKey("cd_formation.id"), nullable=True, index=True
    )
    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id"), nullable=True, index=True
    )
    #: вводная обстановка по сценарию учения
    scenario: Mapped[str | None] = mapped_column(Text)
    participants: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: оценка из CD_DRILL_OUTCOMES; заполняется вместе с held_on
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: анализ: замечания, время сбора, выводы и меры
    findings: Mapped[str | None] = mapped_column(Text)

    formation: Mapped[CivilDefenseFormation | None] = relationship(backref="drills")
    site: Mapped[Site | None] = relationship(backref="cd_drills")

    __table_args__ = (
        Index("ix_cd_drill_tenant_planned", "tenant_id", "planned_on"),
    )
