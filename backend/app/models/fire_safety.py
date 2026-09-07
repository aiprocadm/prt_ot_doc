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

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text
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
    # Разд. 54.1 «испытания (напр., пожарные лестницы, водопровод)»: у работы
    # должен быть объект, иначе испытание некуда записать.
    "fire_escape",  # наружная пожарная лестница, ограждение кровли
    "water_supply",  # противопожарный водопровод (водоотдача)
)


#: Состояние средства в парке — ЗАКРЫТЫЙ словарь (срез-111). До него ``status``
#: был свободной строкой с умолчанием ``active``, и это молча ломало счёт:
#: просрочки везде считаются ТОЛЬКО по средствам «в эксплуатации», а записать
#: туда можно было любое слово — «списан», «Списано», «на складе» — и средство
#: исчезало из готовности к проверке МЧС без единого возражения.
#:
#: Слова взяты у транспортных средств и технических устройств ОПО дословно:
#: одинаковый смысл — одинаковые слова (прецедент состояний ТС, срез-1 БДД).
FIRE_EQUIPMENT_STATUSES: dict[str, str] = {
    "active": "В эксплуатации",
    "suspended": "Не эксплуатируется",
    "decommissioned": "Списано",
}

#: Состояние, при котором средство участвует в счёте просрочек. Списанный
#: огнетушитель с просроченной перезарядкой — не нарушение, а история; так же
#: считают контуры БДД и ПромБеза.
FIRE_EQUIPMENT_ACTIVE_STATUS = "active"


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


#: Виды тренировок и учений (Доп. №1 разд. 54.1 «Тренировки и учения»).
#: ЗАКРЫТЫЙ словарь по тому же доводу, что у видов инструктажа (срез-3):
#: свободная строка («эвакуация», «Эвакуация», «evac») делает требуемый
#: «анализ» невозможным — считать было бы нечего.
FIRE_DRILL_KINDS: dict[str, str] = {
    "evacuation": "Тренировка по эвакуации",
    "fire_fighting": "Тренировка по применению первичных средств пожаротушения",
    "joint": "Совместное учение с подразделениями пожарной охраны",
}

#: Результат проведённой тренировки — тоже закрытый словарь: «анализ» это
#: сравнимая оценка, а не пересказ своими словами (пересказ живёт в findings).
FIRE_DRILL_OUTCOMES: dict[str, str] = {
    "passed": "Проведена, задачи выполнены",
    "with_remarks": "Проведена с замечаниями",
    "failed": "Задачи не выполнены",
}


class FireDrill(TenantBaseModel, SoftDeleteMixin):
    """Тренировка/учение по ПБ: план-график, протокол проведения, анализ.

    До этой таблицы дисциплина умела ВЫПУСТИТЬ программу тренировки документом
    (комплект ПБ, «Программа практической тренировки по эвакуации»), но не
    умела её УЧЕСТЬ: вопрос «когда была последняя и не просрочена ли
    запланированная» не имел ответа в данных.
    """

    __tablename__ = "fire_drill"

    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    #: план-график: дата, на которую тренировка назначена (обязательна —
    #: тренировка рождается ЗАПЛАНИРОВАННОЙ, иначе плана-графика нет)
    planned_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: протокол: дата фактического проведения; NULL — ещё не проводилась
    held_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: вводная обстановка по сценарию
    scenario: Mapped[str | None] = mapped_column(Text)
    #: число участников (для протокола)
    participants: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: оценка из FIRE_DRILL_OUTCOMES; заполняется вместе с held_on
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: анализ: замечания, время эвакуации, выводы и меры
    findings: Mapped[str | None] = mapped_column(Text)

    site: Mapped[Site | None] = relationship(backref="fire_drills")

    __table_args__ = (
        Index("ix_fire_drill_tenant_planned", "tenant_id", "planned_on"),
    )


#: Виды регламентных работ (разд. 54.1 «ТО систем ПБ, испытания… устранение»).
FIRE_MAINTENANCE_KINDS: dict[str, str] = {
    "recharge": "Перезарядка",
    "inspection": "Техническое обслуживание и поверка",
    "test": "Испытание",
    "repair": "Ремонт и устранение замечаний",
}

#: Результат работы. Закрытый словарь: «исправно» и «неисправно» должны
#: считаться, а не пересказываться — пересказ живёт в notes.
FIRE_MAINTENANCE_RESULTS: dict[str, str] = {
    "passed": "Исправно",
    "with_remarks": "Исправно с замечаниями",
    "failed": "Неисправно",
}

#: Результаты, при которых средство считается пригодным к дальнейшей работе, а
#: значит следующий срок можно переносить. «Неисправно» срок НЕ двигает —
#: иначе просрочка исчезла бы с экрана, а неисправность осталась.
FIRE_MAINTENANCE_PASSING_RESULTS: frozenset[str] = frozenset({"passed", "with_remarks"})

#: Какой срок средства переносит работа этого вида.
FIRE_MAINTENANCE_DUE_FIELD: dict[str, str] = {
    "recharge": "recharge_due",
    "inspection": "inspection_due",
    "test": "inspection_due",
    "repair": "inspection_due",
}


class FireMaintenanceRecord(TenantBaseModel, SoftDeleteMixin):
    """Выполненная работа по средству ПБ: ТО, поверка, испытание, ремонт.

    ДО этой таблицы у средства хранился только СЛЕДУЮЩИЙ срок, и отметить
    выполненную работу можно было единственным способом — затереть срок; от
    самой работы не оставалось следа. Инспектор спрашивает не «когда следующая
    поверка», а «покажите, что предыдущая была».
    """

    __tablename__ = "fire_maintenance"

    equipment_id: Mapped[str] = mapped_column(
        ForeignKey("fire_safety_equipment.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    #: дата ФАКТИЧЕСКОГО выполнения — запись о работе это свидетельство, не план
    performed_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: кто выполнил: подрядчик с реквизитами акта или свой работник
    performer: Mapped[str | None] = mapped_column(String(255))
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    #: замечания и что устранено
    notes: Mapped[str | None] = mapped_column(Text)
    #: срок следующей такой же работы; им же двигается срок у средства
    next_due: Mapped[date | None] = mapped_column(Date, nullable=True)

    equipment: Mapped[FireSafetyEquipment] = relationship(backref="maintenance_records")

    __table_args__ = (
        Index("ix_fire_maintenance_tenant_performed", "tenant_id", "performed_on"),
    )


#: Виды документов ПБ — ровно перечень ТЗ (разд. 54.1 «Документы ПБ»):
#: приказы, инструкции о мерах ПБ ОБЩЕОБЪЕКТОВЫЕ И ПО ПОМЕЩЕНИЯМ (это разные
#: виды: общеобъектовая одна на объект, по помещениям их столько, сколько
#: пожароопасных помещений), планы эвакуации, регламенты, декларация, журналы.
FIRE_DOCUMENT_KINDS: dict[str, str] = {
    "order": "Приказ",
    "instruction_general": "Инструкция о мерах ПБ (общеобъектовая)",
    "instruction_room": "Инструкция о мерах ПБ (по помещению)",
    "evacuation_plan": "План эвакуации",
    "regulation": "Регламент",
    "declaration": "Декларация пожарной безопасности",
    "journal": "Журнал",
}

#: Состояние документа словами. Значения — дословно ядровые
#: (``app.domains.shared.ContingentItemStatus``), чтобы словарь состояний в
#: продукте был один; сам импорт запрещён гардом границ контекстов (ARCH-3),
#: см. ``_document_status`` в ручках контура.
FIRE_DOCUMENT_STATUS_TITLES: dict[str, str] = {
    "ok": "Действует",
    "due_soon": "Скоро пересмотр",
    "overdue": "Просрочен пересмотр",
}


class FireSafetyDocument(TenantBaseModel, SoftDeleteMixin):
    """Учётная карточка документа ПБ: что есть у объекта и не пора ли пересмотр.

    Почему НЕ ядровой ``Document``: у того ``template_id`` NOT NULL, поэтому
    документ, который платформа не выпускала (декларация, поданная в МЧС; план
    эвакуации, нарисованный подрядчиком), в реестр ядра не заводится вовсе.
    Плюс у ядра нет ни вида документа (тип выводится из свободной строки
    ``Template.domain``), ни срока пересмотра. Ядро переиспользуется там, где
    оно есть: ссылка ``document_id`` на выпущенный фабрикой документ и
    ЕДИНЫЙ СЛОВАРЬ состояний срока (``ContingentItemStatus``); сам импорт
    классификатора запрещён гардом ARCH-3 — см. ``_document_status``.
    """

    __tablename__ = "fire_document"

    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    #: номер приказа/декларации — как в оригинале
    number: Mapped[str | None] = mapped_column(String(64))
    #: помещение для инструкции по помещению — свободный текст
    #: (реестра помещений в ядре нет, тот же довод, что у средств ПБ)
    location: Mapped[str | None] = mapped_column(String(255))
    approved_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: срок пересмотра/актуализации; NULL — документ бессрочный
    #: (прецедент реестра документов подрядчиков)
    review_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    responsible: Mapped[str | None] = mapped_column(String(255))
    #: если документ выпущен документной фабрикой — ссылка на него; иначе NULL
    #: (бумага из МЧС или от подрядчика существует вне платформы)
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("document.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text)

    site: Mapped[Site | None] = relationship(backref="fire_documents")

    __table_args__ = (
        Index("ix_fire_document_tenant_kind", "tenant_id", "kind"),
        Index("ix_fire_document_tenant_review", "tenant_id", "review_due"),
    )
