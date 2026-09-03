"""Схемы контура БДД (Доп. №1 разд. 56.2)."""

from __future__ import annotations

from datetime import date, datetime

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
    #: срез-3: путевые листы. Реестр листов растёт каждую смену, поэтому в
    #: сводке он считается ЗА ОКНО, а не за всё время: «сколько листов у нас
    #: за три года» — не тот вопрос, на который смотрят утром
    waybill_window_days: int = 0
    waybills_total: int = 0
    #: ключи всегда все три, чтобы «ноль аннулированных» отличался от
    #: «поле не пришло»
    waybills_by_status: dict[str, int] = Field(default_factory=dict)
    #: листы, где обязательная отметка НЕ ПРОЙДЕНА — выпуск с нарушением
    waybills_release_blocked: int = 0
    #: листы, где обязательная отметка не внесена — дыра в учёте, а НЕ
    #: вердикт о нарушении (разные вещи, как «нет сведений» и «просрочено»)
    waybills_release_unconfirmed: int = 0
    #: срез-4: ДТП. Окно ГОДОВОЕ, а не месячное как у листов: ДТП редки, и за
    #: месяц их обычно ноль — по такому окну об аварийности судить нельзя
    accident_window_days: int = 0
    accidents_total: int = 0
    #: ключи всегда все три, чтобы «ноль с погибшими» отличался от
    #: «поле не пришло»
    accidents_by_consequences: dict[str, int] = Field(default_factory=dict)
    #: ФАКТЫ, а не оценка тяжести: числа людей
    injured_total: int = 0
    fatalities_total: int = 0
    #: ДТП, по которым не заведено ни одного мероприятия и нет связи с
    #: расследованием — дыра в разборе, а не вердикт «разобрано плохо»
    accidents_without_follow_up: int = 0
    #: срез-5: инструктажи водителей по БДД. Свой реестр НЕ заводится —
    #: механизм инструктажей ядровой, здесь только счёт по видам БДД.
    #: ГРАНИЦА: просрочка считается по ВНЕСЁННОМУ сроку, а не по норме —
    #: кого и как часто инструктировать, платформа не решает
    road_briefings_total: int = 0
    road_briefings_overdue: int = 0


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


class WaybillCreate(BaseSchema):
    """Выписка путевого листа.

    Номера машины и фамилии здесь НЕТ: лист ссылается на реестр ТС и на
    карточку водителя. Отметки контроля можно не заполнять — свежий лист
    выписывается до осмотра, и это законное состояние «сведений нет».
    """

    number: str = Field(min_length=1, max_length=32)
    vehicle_id: str = Field(min_length=1, max_length=36)
    driver_id: str = Field(min_length=1, max_length=36)
    issued_on: date
    departure_at: datetime | None = None
    return_at: datetime | None = None
    pre_trip_medical: str = Field(default="not_recorded", min_length=1, max_length=16)
    post_trip_medical: str = Field(default="not_recorded", min_length=1, max_length=16)
    pre_trip_technical: str = Field(default="not_recorded", min_length=1, max_length=16)
    status: str = Field(default="issued", min_length=1, max_length=16)
    notes: str | None = None


class WaybillUpdate(BaseSchema):
    """Правка листа. Машину и водителя сменить нельзя — это другой рейс."""

    number: str | None = Field(default=None, min_length=1, max_length=32)
    issued_on: date | None = None
    departure_at: datetime | None = None
    return_at: datetime | None = None
    pre_trip_medical: str | None = Field(default=None, min_length=1, max_length=16)
    post_trip_medical: str | None = Field(default=None, min_length=1, max_length=16)
    pre_trip_technical: str | None = Field(default=None, min_length=1, max_length=16)
    status: str | None = Field(default=None, min_length=1, max_length=16)
    notes: str | None = None


class WaybillRead(BaseSchema):
    """Лист вместе с вердиктом о выпуске и временем в рейсе.

    ГРАНИЦА: полей «законен ли выпуск» и «уложился ли водитель в режим труда и
    отдыха» здесь НЕТ. Обязательность послерейсового осмотра и норма времени
    следуют из вида перевозок и суммирования за неделю — таких данных в
    системе нет.
    """

    id: str
    number: str
    vehicle_id: str
    #: госномер и марка — из реестра ТС, в листе не хранятся
    vehicle_plate: str
    vehicle_brand_model: str
    driver_id: str
    #: ФИО — из ядрового ``Person`` через карточку водителя
    driver_name: str
    driver_license_number: str
    issued_on: date
    departure_at: datetime | None = None
    return_at: datetime | None = None
    #: СЧИТАЕТСЯ ПРИ ЧТЕНИИ из пары выезд/возвращение; ``null`` — хотя бы одна
    #: дата не внесена. Это ВРЕМЯ В РЕЙСЕ, а не время за рулём: сколько из
    #: рейса человек реально вёл машину, платформа не знает
    trip_hours: float | None = None
    pre_trip_medical: str
    pre_trip_medical_label: str
    post_trip_medical: str
    post_trip_medical_label: str
    pre_trip_technical: str
    pre_trip_technical_label: str
    #: confirmed / unconfirmed / blocked — считается ПРИ ЧТЕНИИ из ДВУХ
    #: обязательных отметок (предрейсовые медосмотр и техконтроль).
    #: Послерейсовый в вердикт не входит — он обязателен не всем
    release_status: str
    release_status_label: str
    status: str
    status_label: str
    notes: str | None = None


class WaybillPage(BaseSchema):
    items: list[WaybillRead]
    total: int


class RoadAccidentCreate(BaseSchema):
    """Регистрация ДТП.

    Полей «тяжесть», «разобрано» и «виноват ли наш водитель» здесь НЕТ:
    тяжесть считается из чисел, состояние разбора — из связей, а вину
    устанавливают ГИБДД и суд. Вносится ``fault`` по их документам, и по
    умолчанию она «не установлена».
    """

    occurred_at: datetime
    place: str = Field(min_length=1, max_length=255)
    vehicle_id: str = Field(min_length=1, max_length=36)
    #: водителя может не быть: в стоящую машину въезжают и без него
    driver_id: str | None = Field(default=None, max_length=36)
    kind: str = Field(min_length=1, max_length=24)
    injured_count: int = Field(default=0, ge=0)
    fatalities_count: int = Field(default=0, ge=0)
    fault: str = Field(default="not_established", min_length=1, max_length=24)
    gibdd_reference: str | None = Field(default=None, max_length=128)
    #: связь с ядровым расследованием; пусто — законное состояние
    incident_id: str | None = Field(default=None, max_length=36)
    description: str | None = None


class RoadAccidentUpdate(BaseSchema):
    """Правка. Машину сменить нельзя — это другое ДТП."""

    occurred_at: datetime | None = None
    place: str | None = Field(default=None, min_length=1, max_length=255)
    driver_id: str | None = Field(default=None, max_length=36)
    kind: str | None = Field(default=None, min_length=1, max_length=24)
    injured_count: int | None = Field(default=None, ge=0)
    fatalities_count: int | None = Field(default=None, ge=0)
    fault: str | None = Field(default=None, min_length=1, max_length=24)
    gibdd_reference: str | None = Field(default=None, max_length=128)
    incident_id: str | None = Field(default=None, max_length=36)
    description: str | None = None


class RoadAccidentRead(BaseSchema):
    """ДТП вместе с последствиями и состоянием разбора.

    ГРАНИЦА: полей «виновата ли организация», «достаточны ли мероприятия» и
    «разобрано хорошо» здесь НЕТ. Состояние разбора — факт о незакрытых
    мероприятиях, а не оценка их качества.
    """

    id: str
    occurred_at: datetime
    place: str
    vehicle_id: str
    #: госномер — из реестра ТС, в записи о ДТП не хранится
    vehicle_plate: str
    driver_id: str | None = None
    #: ФИО — из ядрового ``Person`` через карточку водителя; пусто, если
    #: водителя за рулём не было
    driver_name: str | None = None
    kind: str
    kind_label: str
    injured_count: int
    fatalities_count: int
    #: damage_only / injured / fatal — СЧИТАЕТСЯ из чисел, не хранится
    consequences: str
    consequences_label: str
    fault: str
    fault_label: str
    gibdd_reference: str | None = None
    incident_id: str | None = None
    description: str | None = None
    #: мероприятия живут в ядровом CAPA; здесь только их счёт
    capa_total: int = 0
    capa_open: int = 0
    #: not_started / open / closed — СЧИТАЕТСЯ из связей: своего статуса
    #: «разобрано» у ДТП нет, иначе он разошёлся бы с мероприятиями
    follow_up: str
    follow_up_label: str


class RoadAccidentPage(BaseSchema):
    items: list[RoadAccidentRead]
    total: int
