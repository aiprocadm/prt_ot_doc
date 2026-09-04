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
    #: ГРАНИЦА: поля «предлагаемый норматив» здесь НЕТ — ПДВ устанавливается
    #: проектом нормативов. Превышение появилось только со срезом ПЭК и
    #: считается по ЗАМЕРУ: это сравнение двух внесённых чисел, а не вывод
    #: платформы о самом нормативе
    emission_sources: int = 0
    emission_sources_without_norms: int = 0
    emission_norms: int = 0
    emission_permits_overdue: int = 0
    #: разд. 55.2 «ПЭК и план-график замеров»
    monitoring_plan_items: int = 0
    monitoring_overdue: int = 0
    measurements_this_year: int = 0
    measurements_exceeded: int = 0
    #: разд. 55.2 «водопользование». Забор и сброс считаются РАЗДЕЛЬНО: это
    #: разные величины, и складывать их в одну цифру нельзя.
    #: ГРАНИЦА: полей «требуется ли разрешение» и «норматив сброса» здесь НЕТ —
    #: и то и другое устанавливает орган
    water_points: int = 0
    water_permits_overdue: int = 0
    water_intake_cubic_meters: Decimal = Decimal("0.000")
    water_discharge_cubic_meters: Decimal = Decimal("0.000")
    water_over_limit: int = 0
    #: разд. 55.3 «плата за НВОС» за текущий год.
    #: ГРАНИЦА: полей «предлагаемый коэффициент» и «обязана ли организация
    #: платить» здесь НЕТ — коэффициент устанавливается законом и решением
    #: органа, а плательщика определяет категория объекта
    fee_lines: int = 0
    #: строки, для которых ставка не внесена: их сумма НЕ считается нулём и в
    #: итог не попадает — иначе итог выглядел бы полным
    fee_lines_without_rate: int = 0
    fee_total_rubles: Decimal = Decimal("0.00")
    #: Доп. №1 разд. 57.4: открытые происшествия, размеченные этой дисциплиной
    #: (срез-49). Формула одна на контуры и разрез директора —
    #: ``app.services.discipline_incidents``; «не закрыто и не отменено».
    #: Неразмеченные сюда не попадают: контур не угадывает дисциплину.
    incidents_open: int = 0


class NvosFeeRateCreate(BaseSchema):
    year: int = Field(ge=2000, le=2100)
    impact_kind: str = Field(min_length=1, max_length=16)
    subject: str = Field(min_length=1, max_length=255)
    rate_per_ton: Decimal = Field(ge=0)
    source_document: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class NvosFeeRateUpdate(BaseSchema):
    rate_per_ton: Decimal | None = Field(default=None, ge=0)
    source_document: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class NvosFeeRateRead(BaseSchema):
    id: str
    year: int
    impact_kind: str
    impact_kind_label: str
    subject: str
    rate_per_ton: Decimal
    source_document: str | None = None
    notes: str | None = None


class NvosFeeRatePage(BaseSchema):
    items: list[NvosFeeRateRead]
    total: int


class NvosFeeLineCreate(BaseSchema):
    year: int = Field(ge=2000, le=2100)
    #: квартал, он же авансовый платёж
    quarter: int = Field(ge=1, le=4)
    impact_kind: str = Field(min_length=1, max_length=16)
    subject: str = Field(min_length=1, max_length=255)
    mass_tons: Decimal = Field(ge=0)
    #: ноль обнулил бы плату — такого коэффициента не бывает
    coefficient: Decimal = Field(default=Decimal("1.00"), gt=0, le=200)
    notes: str | None = None


class NvosFeeLineUpdate(BaseSchema):
    mass_tons: Decimal | None = Field(default=None, ge=0)
    coefficient: Decimal | None = Field(default=None, gt=0, le=200)
    notes: str | None = None


class NvosFeeLineRead(BaseSchema):
    """Строка расчёта вместе с найденной ставкой и суммой.

    Сумма НЕ хранится: считается при чтении, поэтому исправленная ставка сразу
    доходит до всех строк своего года.
    """

    id: str
    year: int
    quarter: int
    impact_kind: str
    impact_kind_label: str
    subject: str
    mass_tons: Decimal
    coefficient: Decimal
    notes: str | None = None
    #: found / missing — ставка ищется по ГОДУ строки
    rate_status: str
    rate_status_label: str
    rate_per_ton: Decimal | None = None
    #: None, а НЕ ноль, когда ставка не внесена: ноль читался бы как
    #: «платить нечего»
    amount_rubles: Decimal | None = None


class NvosFeeLinePage(BaseSchema):
    items: list[NvosFeeLineRead]
    total: int


class WaterUsagePointCreate(BaseSchema):
    facility_id: str = Field(min_length=1, max_length=36)
    point_number: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    kind: str = Field(min_length=1, max_length=16)
    water_body: str | None = Field(default=None, max_length=255)
    permit_number: str | None = Field(default=None, max_length=64)
    permit_valid_until: date | None = None
    annual_limit_cubic_meters: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class WaterUsagePointUpdate(BaseSchema):
    point_number: str | None = Field(default=None, min_length=1, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    kind: str | None = Field(default=None, min_length=1, max_length=16)
    water_body: str | None = Field(default=None, max_length=255)
    permit_number: str | None = Field(default=None, max_length=64)
    permit_valid_until: date | None = None
    annual_limit_cubic_meters: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class WaterUsagePointRead(BaseSchema):
    """Точка водопользования вместе с состоянием разрешения и объёмом за год.

    ГРАНИЦА: полей «требуется ли разрешение» и «предлагаемый лимит» здесь НЕТ.
    """

    id: str
    facility_id: str
    point_number: str
    name: str
    kind: str
    kind_label: str
    water_body: str | None = None
    permit_number: str | None = None
    permit_valid_until: date | None = None
    annual_limit_cubic_meters: Decimal | None = None
    notes: str | None = None
    #: ok / due_soon / overdue — пустой срок означает «бессрочно»
    permit_status: str
    permit_status_label: str
    #: сумма внесённых объёмов за текущий год, м³
    volume_this_year: Decimal = Decimal("0.000")
    #: превышение — ФАКТ по внесённому лимиту; без лимита всегда False
    over_limit: bool = False


class WaterUsagePointPage(BaseSchema):
    items: list[WaterUsagePointRead]
    total: int


class WaterUsageRecordCreate(BaseSchema):
    point_id: str = Field(min_length=1, max_length=36)
    period_year: int = Field(ge=2000, le=2100)
    #: месяц — единица учёта водопользования
    period_month: int = Field(ge=1, le=12)
    volume_cubic_meters: Decimal = Field(ge=0)
    basis: str = Field(min_length=1, max_length=16)
    meter_number: str | None = Field(default=None, max_length=64)
    notes: str | None = None


class WaterUsageRecordUpdate(BaseSchema):
    volume_cubic_meters: Decimal | None = Field(default=None, ge=0)
    basis: str | None = Field(default=None, min_length=1, max_length=16)
    meter_number: str | None = Field(default=None, max_length=64)
    notes: str | None = None


class WaterUsageRecordRead(BaseSchema):
    id: str
    point_id: str
    period_year: int
    period_month: int
    #: «март 2026» — месяц числом читается хуже, чем словом
    period_label: str
    volume_cubic_meters: Decimal
    basis: str
    basis_label: str
    meter_number: str | None = None
    notes: str | None = None


class WaterUsageRecordPage(BaseSchema):
    items: list[WaterUsageRecordRead]
    total: int


class MonitoringPlanItemCreate(BaseSchema):
    source_id: str = Field(min_length=1, max_length=36)
    substance: str = Field(min_length=1, max_length=255)
    #: 1..60 месяцев: ноль означал бы «никогда», а пять лет — предел, за
    #: которым строка графика перестаёт быть графиком
    periodicity_months: int = Field(ge=1, le=60)
    next_due_on: date
    method: str | None = Field(default=None, max_length=255)
    laboratory: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class MonitoringPlanItemUpdate(BaseSchema):
    substance: str | None = Field(default=None, min_length=1, max_length=255)
    periodicity_months: int | None = Field(default=None, ge=1, le=60)
    next_due_on: date | None = None
    method: str | None = Field(default=None, max_length=255)
    laboratory: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class MonitoringPlanItemRead(BaseSchema):
    """Строка плана-графика ПЭК.

    ГРАНИЦА: полей «требуемая периодичность» и «нужен ли ПЭК» здесь НЕТ —
    периодичность берётся из утверждённой программы ПЭК.
    """

    id: str
    source_id: str
    substance: str
    periodicity_months: int
    #: «раз в квартал» и подобное; нетиповой срок — «раз в N месяцев»
    periodicity_label: str
    next_due_on: date
    method: str | None = None
    laboratory: str | None = None
    notes: str | None = None
    #: ok / due_soon / overdue — считается ПРИ ЧТЕНИИ по плановой дате
    status: str
    status_label: str
    #: дата последнего внесённого замера по этой строке
    last_measured_on: date | None = None


class MonitoringPlanItemPage(BaseSchema):
    items: list[MonitoringPlanItemRead]
    total: int


class EmissionMeasurementCreate(BaseSchema):
    #: строка плана НЕОБЯЗАТЕЛЬНА: замер по предписанию делают вне графика
    plan_id: str | None = Field(default=None, max_length=36)
    source_id: str = Field(min_length=1, max_length=36)
    substance: str = Field(min_length=1, max_length=255)
    measured_on: date
    value_grams_per_second: Decimal = Field(ge=0)
    protocol_number: str | None = Field(default=None, max_length=64)
    laboratory: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class EmissionMeasurementUpdate(BaseSchema):
    measured_on: date | None = None
    value_grams_per_second: Decimal | None = Field(default=None, ge=0)
    protocol_number: str | None = Field(default=None, max_length=64)
    laboratory: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class EmissionMeasurementRead(BaseSchema):
    """Замер ПЭК вместе с итогом сравнения.

    Итог НЕ ХРАНИТСЯ в базе: норматив со временем меняется, и сохранённый
    вывод пережил бы новый норматив.
    """

    id: str
    plan_id: str | None = None
    source_id: str
    substance: str
    measured_on: date
    value_grams_per_second: Decimal
    protocol_number: str | None = None
    laboratory: str | None = None
    notes: str | None = None
    #: норматив, с которым сравнивали (если он внесён)
    norm_grams_per_second: Decimal | None = None
    #: within / exceeded / no_norm / no_single_limit
    comparison: str
    comparison_label: str


class EmissionMeasurementPage(BaseSchema):
    items: list[EmissionMeasurementRead]
    total: int
