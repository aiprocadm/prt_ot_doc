"""Схемы контура ПромБеза (Доп. №1 разд. 54.2): реестр ОПО."""

from __future__ import annotations

from datetime import date

from pydantic import Field

from app.schemas.base import BaseSchema


class HazardousFacilityCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    #: обязателен: ОПО без номера в госреестре не существует
    register_number: str = Field(min_length=1, max_length=64)
    hazard_class: str = Field(min_length=1, max_length=8)
    site_id: str | None = Field(default=None, min_length=1, max_length=36)
    registered_on: date | None = None
    excluded_on: date | None = None
    status: str = Field(default="registered", max_length=16)
    responsible: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class HazardousFacilityUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    register_number: str | None = Field(default=None, min_length=1, max_length=64)
    hazard_class: str | None = Field(default=None, min_length=1, max_length=8)
    site_id: str | None = Field(default=None, max_length=36)
    registered_on: date | None = None
    excluded_on: date | None = None
    status: str | None = Field(default=None, max_length=16)
    responsible: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class HazardousFacilityRead(BaseSchema):
    id: str
    name: str
    register_number: str
    hazard_class: str
    #: класс и состояние словами — перевод делает сервер, экран его не дублирует
    hazard_class_label: str
    site_id: str | None = None
    registered_on: date | None = None
    excluded_on: date | None = None
    status: str
    status_label: str
    responsible: str | None = None
    notes: str | None = None


class HazardousFacilityPage(BaseSchema):
    items: list[HazardousFacilityRead]
    total: int


class TechnicalDeviceCreate(BaseSchema):
    #: обязателен: экспертиза и надзор идут по зарегистрированному объекту,
    #: устройство «ничьё» невозможно предъявить проверяющему
    facility_id: str = Field(min_length=1, max_length=36)
    kind: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    serial_number: str | None = Field(default=None, max_length=64)
    commissioned_on: date | None = None
    lifetime_until: date | None = None
    epb_conclusion_number: str | None = Field(default=None, max_length=64)
    epb_registered_on: date | None = None
    epb_valid_until: date | None = None
    status: str = Field(default="in_operation", max_length=16)
    notes: str | None = None


class TechnicalDeviceUpdate(BaseSchema):
    facility_id: str | None = Field(default=None, min_length=1, max_length=36)
    kind: str | None = Field(default=None, min_length=1, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    serial_number: str | None = Field(default=None, max_length=64)
    commissioned_on: date | None = None
    lifetime_until: date | None = None
    epb_conclusion_number: str | None = Field(default=None, max_length=64)
    epb_registered_on: date | None = None
    epb_valid_until: date | None = None
    status: str | None = Field(default=None, max_length=16)
    notes: str | None = None


class TechnicalDeviceRead(BaseSchema):
    id: str
    facility_id: str
    kind: str
    kind_label: str
    name: str
    serial_number: str | None = None
    commissioned_on: date | None = None
    lifetime_until: date | None = None
    epb_conclusion_number: str | None = None
    epb_registered_on: date | None = None
    epb_valid_until: date | None = None
    status: str
    status_label: str
    notes: str | None = None
    #: ok / due_soon / overdue / absent — считается ПРИ ЧТЕНИИ.
    #: «absent» — отдельное состояние, а не разновидность просрочки
    epb_status: str
    epb_status_label: str
    #: назначенный срок службы истёк — факт из данных, не суждение о том,
    #: обязана ли экспертиза быть проведена
    past_lifetime: bool = False
    #: разд. 54.2 «история работ»: последняя ПОДТВЕРЖДЁННАЯ работа — срок без
    #: неё это обещание, а не доказательство. Считается при чтении
    last_work_on: date | None = None
    last_work_result: str | None = None


class TechnicalDevicePage(BaseSchema):
    items: list[TechnicalDeviceRead]
    total: int


class DeviceWorkCreate(BaseSchema):
    device_id: str = Field(min_length=1, max_length=36)
    kind: str = Field(min_length=1, max_length=32)
    performed_on: date
    result: str = Field(min_length=1, max_length=32)
    performer: str | None = Field(default=None, max_length=255)
    #: обязателен для вида ``epb`` — см. валидацию в ручке
    conclusion_number: str | None = Field(default=None, max_length=64)
    notes: str | None = None
    next_due: date | None = None


class DeviceWorkRead(BaseSchema):
    id: str
    device_id: str
    kind: str
    kind_label: str
    performed_on: date
    result: str
    result_label: str
    performer: str | None = None
    conclusion_number: str | None = None
    notes: str | None = None
    next_due: date | None = None
    #: перенесла ли эта работа срок эксплуатации устройства; переносит только
    #: положительная ЭПБ
    shifted_due: bool = False


class DeviceWorkPage(BaseSchema):
    items: list[DeviceWorkRead]
    total: int


class PcPlanCreate(BaseSchema):
    year: int = Field(ge=2000, le=2100)
    title: str = Field(min_length=1, max_length=255)
    responsible: str | None = Field(default=None, max_length=255)
    approved_on: date | None = None
    status: str = Field(default="draft", max_length=16)
    notes: str | None = None


class PcPlanUpdate(BaseSchema):
    year: int | None = Field(default=None, ge=2000, le=2100)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    responsible: str | None = Field(default=None, max_length=255)
    approved_on: date | None = None
    status: str | None = Field(default=None, max_length=16)
    notes: str | None = None


class PcPlanRead(BaseSchema):
    id: str
    year: int
    title: str
    responsible: str | None = None
    approved_on: date | None = None
    status: str
    status_label: str
    notes: str | None = None
    #: сколько мероприятий в плане и сколько из них просрочено — считается
    #: при чтении, чтобы план был виден одной строкой
    measures_total: int = 0
    measures_overdue: int = 0


class PcPlanPage(BaseSchema):
    items: list[PcPlanRead]
    total: int


class PcMeasureCreate(BaseSchema):
    plan_id: str = Field(min_length=1, max_length=36)
    section: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=255)
    due_on: date
    responsible: str | None = Field(default=None, max_length=255)
    status: str = Field(default="planned", max_length=16)
    completed_on: date | None = None
    result: str | None = None


class PcMeasureUpdate(BaseSchema):
    plan_id: str | None = Field(default=None, min_length=1, max_length=36)
    section: str | None = Field(default=None, min_length=1, max_length=32)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    due_on: date | None = None
    responsible: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, max_length=16)
    completed_on: date | None = None
    result: str | None = None


class PcMeasureRead(BaseSchema):
    id: str
    plan_id: str
    section: str
    section_label: str
    title: str
    due_on: date
    responsible: str | None = None
    #: planned / overdue / done / cancelled — «просрочено» СЧИТАЕТСЯ при чтении
    status: str
    status_label: str
    completed_on: date | None = None
    result: str | None = None


class PcMeasurePage(BaseSchema):
    items: list[PcMeasureRead]
    total: int


class OpoAttestationRead(BaseSchema):
    """Аттестация по промбезопасности глазами дисциплины.

    Сама запись живёт в ЯДРЕ (``Attestation``) — дисциплина её не дублирует, а
    показывает СВОИ записи и добавляет то, чего у ядра нет: имя человека рядом
    и состояние срока словами.

    «Свои» — это записи с областью СВОЕЙ ДИСЦИПЛИНЫ. Здесь стояло «те, у
    которых заполнена область из справочника»: верно, пока справочник был
    перечнем Ростехнадзора, и ложно с разд. 56.2 срез-6, где в нём появилась
    область «ПДД» (проверка знаний водителей).
    """

    id: str
    person_id: str
    person_name: str
    name: str
    area_code: str
    area_label: str
    issued_at: date | None = None
    expires_at: date | None = None
    #: ok / due_soon / overdue / absent — считается ПРИ ЧТЕНИИ
    validity_status: str
    validity_status_label: str


class OpoAttestationPage(BaseSchema):
    items: list[OpoAttestationRead]
    total: int


class IndustrialReadinessRead(BaseSchema):
    """Сводка ПромБеза: сколько объектов и какого класса опасности.

    От класса зависит режим надзора (объекты I и II класса — постоянный
    государственный надзор и обязательная декларация промышленной
    безопасности), поэтому разрез по классам — не украшение, а первое, что
    нужно специалисту и проверяющему.

    Считаются ДЕЙСТВУЮЩИЕ объекты: исключённый из госреестра остаётся в
    системе ради истории, но объектом надзора быть перестаёт.
    """

    total_facilities: int
    #: класс → число действующих объектов; ключи — всегда все четыре, чтобы
    #: «ноль объектов I класса» отличался от «поле не пришло»
    by_class: dict[str, int]
    excluded_facilities: int
    #: разд. 54.2 «технические устройства… ЭПБ, сроки»: считаются только
    #: эксплуатируемые устройства — списанное просрочкой быть не может
    total_devices: int = 0
    epb_overdue: int = 0
    epb_due_soon: int = 0
    #: ФАКТ из данных: назначенный срок службы истёк, а действующего заключения
    #: ЭПБ нет. ГРАНИЦА: платформа НЕ решает, обязана ли экспертиза быть
    #: проведена — это зависит от типа устройства, документации и норм ФНП,
    #: которых в данных нет. Поэтому поля «устройств без ЭПБ» здесь НЕТ.
    devices_past_lifetime_without_epb: int = 0
    #: разд. 54.2 «история работ»: устройства, по которым нет НИ ОДНОЙ записи о
    #: работах — срок стоит, а подтвердить его нечем
    devices_without_work_record: int = 0
    #: разд. 54.2 «аттестация персонала»: считаются ТОЛЬКО записи с областью из
    #: справочника — сводка дисциплины показывает свои записи, а не все
    #: аттестации арендатора
    attestations_total: int = 0
    attestations_overdue: int = 0
    attestations_due_soon: int = 0
    #: разд. 54.2 «производственный контроль». ГРАНИЦА: платформа сообщает
    #: ФАКТ наличия плана на текущий год, но не объявляет его отсутствие
    #: нарушением — обязанность вести ПК зависит от того, эксплуатирует ли
    #: организация ОПО, и полноту сведений определяет специалист.
    current_year_plan_exists: bool = False
    pc_measures_overdue: int = 0
    pc_measures_planned: int = 0
