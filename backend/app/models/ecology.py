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
from decimal import Decimal

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
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


#: Классы опасности отходов, подлежащих ПАСПОРТИЗАЦИИ (разд. 55.2).
#: ЗАКРЫТЫЙ словарь из ЧЕТЫРЁХ значений — и это не описка ТЗ: отходы V класса
#: (практически неопасные) паспортизации не подлежат, паспорт составляется на
#: отходы I–IV класса.
WASTE_HAZARD_CLASSES: dict[str, str] = {
    "I": "I класс — чрезвычайно опасные",
    "II": "II класс — высокоопасные",
    "III": "III класс — умеренно опасные",
    "IV": "IV класс — малоопасные",
}

#: Виды движения отходов (разд. 55.2 «учёт образования/движения/передачи»).
#: Свободная строка сделала бы учёт непересчитываемым, а отчётность 2-ТП —
#: невозможной.
WASTE_MOVEMENT_KINDS: dict[str, str] = {
    "generated": "Образование",
    "accumulated": "Накопление",
    "transferred": "Передача оператору",
    "disposed": "Размещение (захоронение)",
    "neutralized": "Обезвреживание",
    "utilized": "Утилизация",
}


class WastePassport(TenantBaseModel, SoftDeleteMixin):
    """Паспорт отхода I–IV класса: вид отхода, код ФККО, годовой лимит.

    Паспорт — удостоверение ВИДА отхода, а не отдельной партии: он один на код
    ФККО, и по нему ведётся весь учёт движения.
    """

    __tablename__ = "waste_passport"

    facility_id: Mapped[str | None] = mapped_column(
        ForeignKey("nvos_facility.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: код по федеральному классификационному каталогу отходов
    fkko_code: Mapped[str] = mapped_column(String(16), nullable=False)
    hazard_class: Mapped[str] = mapped_column(String(8), nullable=False)
    approved_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: годовой лимит образования/размещения в тоннах — ИЗ ДОКУМЕНТА (НООЛР или
    #: декларации). Платформа лимит НЕ РАССЧИТЫВАЕТ: без внесённого значения
    #: никакого суждения о превышении быть не может.
    annual_limit_tons: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 3), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text)

    facility: Mapped[EnvironmentalFacility | None] = relationship(
        backref="waste_passports"
    )

    __table_args__ = (
        # Один код ФККО — один паспорт: два паспорта на один код это один вид
        # отхода, заведённый дважды, и учёт по нему стал бы враньём.
        UniqueConstraint("tenant_id", "fkko_code", name="uq_waste_passport_fkko"),
    )


class WasteMovement(TenantBaseModel, SoftDeleteMixin):
    """Запись журнала учёта отходов: что, когда, сколько и кому.

    ПОЧЕМУ НЕ ЯДРОВОЙ ``Journal``: у ядровой записи журнала ``person_id``
    NOT NULL, а движение отходов к человеку не привязано вовсе — класть его
    туда значило бы ломать схему ради названия. Журнал учёта отходов и есть
    список этих записей по паспорту.

    ДОГОВОР С ОПЕРАТОРОМ НЕ ДУБЛИРУЕТСЯ: в ядре есть ``Contract`` (контрагент,
    номер, срок, сумма), и запись ссылается на него.
    """

    __tablename__ = "waste_movement"

    passport_id: Mapped[str] = mapped_column(
        ForeignKey("waste_passport.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    happened_on: Mapped[date] = mapped_column(Date, nullable=False)
    quantity_tons: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    #: договор с оператором по обращению с отходами — ссылка на ядро
    contract_id: Mapped[str | None] = mapped_column(
        ForeignKey("contract.id"), nullable=True
    )
    #: контрагент строкой, когда договор в системе не заведён
    counterparty: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

    passport: Mapped[WastePassport] = relationship(backref="movements")

    __table_args__ = (
        Index("ix_waste_movement_tenant_date", "tenant_id", "happened_on"),
    )


#: Типы стационарных источников выбросов (разд. 55.2 «инвентаризация»).
#: Деление на организованные и неорганизованные — основа инвентаризации: у
#: организованного есть устье (труба, аэрационный фонарь), у неорганизованного
#: его нет (открытые склады, площадки), и нормируются они по-разному.
EMISSION_SOURCE_KINDS: dict[str, str] = {
    "organized": "Организованный источник",
    "unorganized": "Неорганизованный источник",
}

#: Состояние разрешения по нормативу выброса. Пустой срок — БЕССРОЧНО, а не
#: «просрочено» (для объектов III категории нормативы могут действовать без
#: срока): тот же выбор, что у срока пересмотра документов ПБ.
EMISSION_NORM_STATUS_TITLES: dict[str, str] = {
    "ok": "Действует",
    "due_soon": "Разрешение скоро истекает",
    "overdue": "Разрешение просрочено",
}


class EmissionSource(TenantBaseModel, SoftDeleteMixin):
    """Стационарный источник выбросов: инвентаризационный номер и тип.

    Принадлежит ОБЪЕКТУ НВОС, а не площадке: инвентаризация и разрешения
    оформляются по зарегистрированному объекту, а объектов на площадке бывает
    несколько.
    """

    __tablename__ = "emission_source"

    facility_id: Mapped[str] = mapped_column(
        ForeignKey("nvos_facility.id"), nullable=False, index=True
    )
    #: номер источника по инвентаризации — нумерация ведётся ПО ОБЪЕКТУ
    source_number: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    inventoried_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text)

    facility: Mapped[EnvironmentalFacility] = relationship(backref="emission_sources")

    __table_args__ = (
        # Номер уникален В ПРЕДЕЛАХ ОБЪЕКТА, а не арендатора: «источник №1»
        # есть у каждого объекта, и запрет на уровне арендатора был бы ложным.
        UniqueConstraint(
            "tenant_id", "facility_id", "source_number", name="uq_emission_source_number"
        ),
    )


class EmissionNorm(TenantBaseModel, SoftDeleteMixin):
    """Норматив выброса (ПДВ) по паре «источник + вещество».

    ПДВ устанавливается по КАЖДОМУ загрязняющему веществу отдельно — одним
    числом на источник его не выразить.

    ГРАНИЦА: платформа норматив НЕ РАССЧИТЫВАЕТ. Он определяется расчётом
    рассеивания в проекте нормативов и утверждается разрешением; исходных
    данных (параметры выброса, метеоусловия, фоновые концентрации) в системе
    нет.
    """

    __tablename__ = "emission_norm"

    source_id: Mapped[str] = mapped_column(
        ForeignKey("emission_source.id"), nullable=False, index=True
    )
    #: наименование загрязняющего вещества — свободная строка НАМЕРЕННО:
    #: перечень веществ ведётся государством и насчитывает сотни позиций,
    #: закрывать его словарём в коде значило бы гарантированно отстать
    substance: Mapped[str] = mapped_column(String(255), nullable=False)
    #: разовый норматив, г/с
    limit_grams_per_second: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 6), nullable=True
    )
    #: валовый норматив, т/год
    limit_tons_per_year: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 3), nullable=True
    )
    permit_number: Mapped[str | None] = mapped_column(String(64))
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text)

    source: Mapped[EmissionSource] = relationship(backref="norms")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", "substance", name="uq_emission_norm_substance"
        ),
        Index("ix_emission_norm_tenant_valid", "tenant_id", "valid_until"),
    )
