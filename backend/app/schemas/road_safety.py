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
