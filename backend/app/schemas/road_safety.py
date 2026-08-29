"""Схемы контура БДД (Доп. №1 разд. 56.2)."""

from __future__ import annotations

from datetime import date

from pydantic import Field

from app.schemas.base import BaseSchema


class VehicleCreate(BaseSchema):
    plate_number: str = Field(min_length=1, max_length=32)
    brand_model: str = Field(min_length=1, max_length=255)
    kind: str = Field(min_length=1, max_length=16)
    status: str = Field(default="in_service", min_length=1, max_length=16)
    vin: str | None = Field(default=None, max_length=32)
    year_made: int | None = Field(default=None, ge=1900, le=2100)
    site_id: str | None = Field(default=None, max_length=36)
    inspection_due: date | None = None
    insurance_due: date | None = None
    license_number: str | None = Field(default=None, max_length=128)
    license_due: date | None = None
    tachograph_installed: bool = False
    tachograph_due: date | None = None
    notes: str | None = None


class VehicleUpdate(BaseSchema):
    plate_number: str | None = Field(default=None, min_length=1, max_length=32)
    brand_model: str | None = Field(default=None, min_length=1, max_length=255)
    kind: str | None = Field(default=None, min_length=1, max_length=16)
    status: str | None = Field(default=None, min_length=1, max_length=16)
    vin: str | None = Field(default=None, max_length=32)
    year_made: int | None = Field(default=None, ge=1900, le=2100)
    site_id: str | None = Field(default=None, max_length=36)
    inspection_due: date | None = None
    insurance_due: date | None = None
    license_number: str | None = Field(default=None, max_length=128)
    license_due: date | None = None
    tachograph_installed: bool | None = None
    tachograph_due: date | None = None
    notes: str | None = None


class VehicleRead(BaseSchema):
    """ТС вместе с состоянием сроков.

    ГРАНИЦА: полей «требуется тахограф», «нужна лицензия» и «соответствует ли
    ТС» здесь НЕТ — это следует из вида перевозок, массы и категории ТС.
    """

    id: str
    plate_number: str
    brand_model: str
    kind: str
    kind_label: str
    status: str
    status_label: str
    vin: str | None = None
    year_made: int | None = None
    site_id: str | None = None
    inspection_due: date | None = None
    insurance_due: date | None = None
    license_number: str | None = None
    license_due: date | None = None
    tachograph_installed: bool = False
    tachograph_due: date | None = None
    notes: str | None = None
    #: missing / ok / due_soon / overdue — считается ПРИ ЧТЕНИИ.
    #: Пустой срок = «сведения не внесены», а НЕ «бессрочно»: у полиса и
    #: диагностической карты бессрочности не бывает
    inspection_status: str
    inspection_status_label: str
    insurance_status: str
    insurance_status_label: str
    #: not_installed / missing / ok / due_soon / overdue
    tachograph_status: str
    tachograph_status_label: str


class VehiclePage(BaseSchema):
    items: list[VehicleRead]
    total: int


class RoadSafetyReadinessRead(BaseSchema):
    """Сводка БДД: парк и сроки документов.

    Просрочки считаются ТОЛЬКО по ТС в эксплуатации: у списанной машины
    просроченный полис это шум, а не проблема.

    ГРАНИЦА: полей «соответствует ли парк» и «требуется тахограф» здесь НЕТ.
    """

    total_vehicles: int
    #: состояние → число; ключи всегда все три, чтобы «ноль списанных»
    #: отличался от «поле не пришло»
    by_status: dict[str, int]
    inspection_overdue: int = 0
    insurance_overdue: int = 0
    tachograph_overdue: int = 0
    #: ТС в эксплуатации, у которых не внесены сведения о диагностической
    #: карте или полисе — это ФАКТ о данных, а не вердикт о нарушении
    documents_missing: int = 0
    #: срез-2: водительский состав. Просрочки — ТОЛЬКО по допущенным: у
    #: отстранённого водителя просроченное удостоверение это шум, а не
    #: проблема (тот же довод, что у списанного ТС)
    total_drivers: int = 0
    #: ключи всегда все три, чтобы «ноль отстранённых» отличался от
    #: «поле не пришло»
    drivers_by_status: dict[str, int] = Field(default_factory=dict)
    driver_license_overdue: int = 0
    #: допущенные водители без внесённого срока удостоверения — ФАКТ о
    #: данных, а не вердикт о нарушении
    driver_license_missing: int = 0


class DriverCreate(BaseSchema):
    """Заведение карточки водителя.

    ФИО здесь НЕТ: человек берётся из ядра по ``person_id``. Отдельного поля
    «стаж, лет» тоже нет — стаж задаётся ДАТОЙ, с которой он идёт.
    """

    person_id: str = Field(min_length=1, max_length=36)
    license_number: str = Field(min_length=1, max_length=32)
    #: хотя бы одна категория: водитель без единой категории — это не водитель
    categories: list[str] = Field(min_length=1)
    license_issued_at: date | None = None
    license_due: date | None = None
    experience_since: date | None = None
    status: str = Field(default="admitted", min_length=1, max_length=16)
    notes: str | None = None


class DriverUpdate(BaseSchema):
    license_number: str | None = Field(default=None, min_length=1, max_length=32)
    categories: list[str] | None = Field(default=None, min_length=1)
    license_issued_at: date | None = None
    license_due: date | None = None
    experience_since: date | None = None
    status: str | None = Field(default=None, min_length=1, max_length=16)
    notes: str | None = None


class DriverRead(BaseSchema):
    """Карточка водителя вместе с состоянием удостоверения и стажем.

    ГРАНИЦА: полей «допущен ли к этой машине», «хватает ли стажа» и
    «соответствует ли водитель» здесь НЕТ — нужная категория и требуемый стаж
    следуют из массы ТС, числа мест и вида перевозок по закону.
    """

    id: str
    person_id: str
    #: ФИО — из ядрового ``Person``, не хранится в карточке водителя
    person_name: str
    personnel_number: str | None = None
    position_title: str | None = None
    license_number: str
    categories: list[str]
    #: те же категории словами, чтобы экран не знал справочника
    category_labels: list[str]
    license_issued_at: date | None = None
    license_due: date | None = None
    experience_since: date | None = None
    #: СЧИТАЕТСЯ ПРИ ЧТЕНИИ от ``experience_since``; ``null`` — дата не
    #: внесена. Числом стаж не хранится: записанное «3 года» через два года
    #: молча становится ложью
    experience_years: int | None = None
    status: str
    status_label: str
    #: missing / ok / due_soon / overdue — считается ПРИ ЧТЕНИИ. Пустой срок =
    #: «сведения не внесены», а НЕ «бессрочно»: у водительского удостоверения
    #: бессрочности не бывает
    license_status: str
    license_status_label: str
    notes: str | None = None


class DriverPage(BaseSchema):
    items: list[DriverRead]
    total: int
