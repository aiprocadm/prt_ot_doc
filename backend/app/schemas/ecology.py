"""Схемы контура экологии (Доп. №1 разд. 55.1): объекты НВОС."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import Field

from app.schemas.base import BaseSchema


class EnvironmentalFacilityCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    #: обязателен: без кода в госреестре объект не считается учтённым
    register_number: str = Field(min_length=1, max_length=64)
    category: str = Field(min_length=1, max_length=8)
    site_id: str | None = Field(default=None, min_length=1, max_length=36)
    registered_on: date | None = None
    actualized_on: date | None = None
    excluded_on: date | None = None
    status: str = Field(default="registered", max_length=16)
    responsible: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class EnvironmentalFacilityUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    register_number: str | None = Field(default=None, min_length=1, max_length=64)
    category: str | None = Field(default=None, min_length=1, max_length=8)
    site_id: str | None = Field(default=None, max_length=36)
    registered_on: date | None = None
    actualized_on: date | None = None
    excluded_on: date | None = None
    status: str | None = Field(default=None, max_length=16)
    responsible: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class EnvironmentalFacilityRead(BaseSchema):
    id: str
    name: str
    register_number: str
    category: str
    #: категория и состояние словами — перевод делает сервер
    category_label: str
    site_id: str | None = None
    registered_on: date | None = None
    actualized_on: date | None = None
    excluded_on: date | None = None
    status: str
    status_label: str
    responsible: str | None = None
    notes: str | None = None


class EnvironmentalFacilityPage(BaseSchema):
    items: list[EnvironmentalFacilityRead]
    total: int


class WastePassportCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    #: обязателен: код ФККО — удостоверение вида отхода
    fkko_code: str = Field(min_length=1, max_length=16)
    hazard_class: str = Field(min_length=1, max_length=8)
    facility_id: str | None = Field(default=None, min_length=1, max_length=36)
    approved_on: date | None = None
    #: годовой лимит в тоннах ИЗ ДОКУМЕНТА (НООЛР/декларация) — не расчёт
    annual_limit_tons: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class WastePassportUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    fkko_code: str | None = Field(default=None, min_length=1, max_length=16)
    hazard_class: str | None = Field(default=None, min_length=1, max_length=8)
    facility_id: str | None = Field(default=None, max_length=36)
    approved_on: date | None = None
    annual_limit_tons: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class WastePassportRead(BaseSchema):
    id: str
    name: str
    fkko_code: str
    hazard_class: str
    #: класс словами — перевод делает сервер
    hazard_class_label: str
    facility_id: str | None = None
    approved_on: date | None = None
    annual_limit_tons: Decimal | None = None
    notes: str | None = None
    #: образование за ТЕКУЩИЙ год — считается при чтении по журналу движений
    generated_this_year_tons: Decimal
    #: превышение лимита. ГРАНИЦА: только если лимит внесён — платформа его не
    #: рассчитывает, он берётся из НООЛР или декларации
    over_limit: bool = False


class WastePassportPage(BaseSchema):
    items: list[WastePassportRead]
    total: int


class WasteMovementCreate(BaseSchema):
    passport_id: str = Field(min_length=1, max_length=36)
    kind: str = Field(min_length=1, max_length=16)
    happened_on: date
    #: масса в тоннах; ноль не принимается — движение без массы ничего не
    #: учитывает, это пустая строка журнала
    quantity_tons: Decimal = Field(gt=0)
    contract_id: str | None = Field(default=None, min_length=1, max_length=36)
    counterparty: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class WasteMovementUpdate(BaseSchema):
    passport_id: str | None = Field(default=None, min_length=1, max_length=36)
    kind: str | None = Field(default=None, min_length=1, max_length=16)
    happened_on: date | None = None
    quantity_tons: Decimal | None = Field(default=None, gt=0)
    contract_id: str | None = Field(default=None, max_length=36)
    counterparty: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class WasteMovementRead(BaseSchema):
    id: str
    passport_id: str
    kind: str
    kind_label: str
    happened_on: date
    quantity_tons: Decimal
    contract_id: str | None = None
    counterparty: str | None = None
    notes: str | None = None


class WasteMovementPage(BaseSchema):
    items: list[WasteMovementRead]
    total: int


class EcologyReadinessRead(BaseSchema):
    """Сводка экологии: сколько объектов НВОС и какой категории.

    От категории зависят режим надзора и состав отчётности, поэтому разрез по
    категориям — первое, что нужно экологу. Считаются объекты НА УЧЁТЕ: снятый
    с учёта остаётся в системе ради истории, но объектом надзора быть
    перестаёт.

    ГРАНИЦА: полей «предлагаемая категория» и «несоответствие категории» здесь
    НЕТ и быть не должно — категорию присваивают при постановке на учёт по
    критериям постановления Правительства, а исходных данных для такого вывода
    в системе нет.
    """

    total_facilities: int
    #: категория → число объектов на учёте; ключи — всегда все четыре, чтобы
    #: «ноль объектов I категории» отличался от «поле не пришло»
    by_category: dict[str, int]
    excluded_facilities: int
    #: объекты, у которых сведения ни разу не актуализировали — факт, а не
    #: нарушение: обязанность актуализировать возникает при изменении
    #: характеристик объекта, а не по календарю
    never_actualized: int
    #: разд. 55.2 «отходы»: паспорта, записи журнала учёта и превышения лимита
    #: (последнее — только по внесённым лимитам)
    waste_passports: int = 0
    waste_movements: int = 0
    waste_over_limit: int = 0
