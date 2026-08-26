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


class EmissionSourceCreate(BaseSchema):
    facility_id: str = Field(min_length=1, max_length=36)
    source_number: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    kind: str = Field(min_length=1, max_length=16)
    location: str | None = Field(default=None, max_length=255)
    inventoried_on: date | None = None
    notes: str | None = None


class EmissionSourceUpdate(BaseSchema):
    facility_id: str | None = Field(default=None, min_length=1, max_length=36)
    source_number: str | None = Field(default=None, min_length=1, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    kind: str | None = Field(default=None, min_length=1, max_length=16)
    location: str | None = Field(default=None, max_length=255)
    inventoried_on: date | None = None
    notes: str | None = None


class EmissionSourceRead(BaseSchema):
    id: str
    facility_id: str
    source_number: str
    name: str
    kind: str
    kind_label: str
    location: str | None = None
    inventoried_on: date | None = None
    notes: str | None = None
    #: сколько нормативов задано по этому источнику — считается при чтении
    norms_count: int = 0


class EmissionSourcePage(BaseSchema):
    items: list[EmissionSourceRead]
    total: int


class EmissionNormCreate(BaseSchema):
    source_id: str = Field(min_length=1, max_length=36)
    substance: str = Field(min_length=1, max_length=255)
    limit_grams_per_second: Decimal | None = Field(default=None, ge=0)
    limit_tons_per_year: Decimal | None = Field(default=None, ge=0)
    permit_number: str | None = Field(default=None, max_length=64)
    valid_until: date | None = None
    notes: str | None = None


class EmissionNormUpdate(BaseSchema):
    source_id: str | None = Field(default=None, min_length=1, max_length=36)
    substance: str | None = Field(default=None, min_length=1, max_length=255)
    limit_grams_per_second: Decimal | None = Field(default=None, ge=0)
    limit_tons_per_year: Decimal | None = Field(default=None, ge=0)
    permit_number: str | None = Field(default=None, max_length=64)
    valid_until: date | None = None
    notes: str | None = None


class EmissionNormRead(BaseSchema):
    id: str
    source_id: str
    substance: str
    limit_grams_per_second: Decimal | None = None
    limit_tons_per_year: Decimal | None = None
    permit_number: str | None = None
    valid_until: date | None = None
    notes: str | None = None
    #: ok / due_soon / overdue — считается ПРИ ЧТЕНИИ; пустой срок = бессрочно
    validity_status: str
    validity_status_label: str


class EmissionNormPage(BaseSchema):
    items: list[EmissionNormRead]
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
    #: разд. 55.2 «выбросы»: инвентаризация источников и нормативы.
    #: ГРАНИЦА: полей «предлагаемый норматив» и «превышение норматива» здесь
    #: НЕТ — ПДВ устанавливается проектом нормативов, а факт выброса меряется
    #: замерами ПЭК (следующий срез)
    emission_sources: int = 0
    emission_sources_without_norms: int = 0
    emission_norms: int = 0
    emission_permits_overdue: int = 0
