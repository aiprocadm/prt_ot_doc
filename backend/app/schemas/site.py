from __future__ import annotations

from pydantic import EmailStr, Field

from app.schemas.base import BaseSchema


class SiteBase(BaseSchema):
    company_id: str = Field(min_length=1, max_length=36)
    branch_id: str | None = Field(default=None, min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=255)
    address: str | None = Field(default=None, max_length=255)
    geo_json: dict | None = None
    hazard_class: str | None = Field(default=None, max_length=32)
    site_type: str | None = Field(default=None, max_length=64)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=32)
    contact_email: EmailStr | None = None
    is_hazardous_production_facility: bool = False
    opo_register_number: str | None = Field(default=None, max_length=64)
    branding_payload: dict = Field(default_factory=dict)


class SiteCreate(SiteBase):
    pass


class SiteUpdate(BaseSchema):
    branch_id: str | None = Field(default=None, min_length=1, max_length=36)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = Field(default=None, max_length=255)
    geo_json: dict | None = None
    hazard_class: str | None = Field(default=None, max_length=32)
    site_type: str | None = Field(default=None, max_length=64)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=32)
    contact_email: EmailStr | None = None
    is_hazardous_production_facility: bool | None = None
    opo_register_number: str | None = Field(default=None, max_length=64)
    branding_payload: dict | None = None


class SiteRead(SiteBase):
    id: str


class SitePage(BaseSchema):
    items: list[SiteRead]
    total: int


class WorkplaceBase(BaseSchema):
    company_id: str = Field(min_length=1, max_length=36)
    site_id: str | None = Field(default=None, min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    location: str | None = Field(default=None, max_length=255)
    working_conditions_class: str | None = Field(default=None, max_length=32)
    hazard_ids: list[str] = Field(default_factory=list)
    document_file_ids: list[str] = Field(default_factory=list)


class WorkplaceCreate(WorkplaceBase):
    pass


class WorkplaceUpdate(BaseSchema):
    site_id: str | None = Field(default=None, min_length=1, max_length=36)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    location: str | None = Field(default=None, max_length=255)
    working_conditions_class: str | None = Field(default=None, max_length=32)
    hazard_ids: list[str] | None = None
    document_file_ids: list[str] | None = None


class WorkplaceRead(WorkplaceBase):
    id: str


class WorkplacePage(BaseSchema):
    items: list[WorkplaceRead]
    total: int


class SiteDisciplineRead(BaseSchema):
    """Одна дисциплина на карточке площадки 360° (BIZ-54-57 срез-3, разд. 57.1).

    Форма — та же, что у светофора клиента (``DirectionReadinessRead``):
    дисциплина на двух экранах обязана выглядеть одинаково, иначе «жёлтый»
    начнут читать по-разному.
    """

    discipline: str
    title: str
    #: green / yellow / red / not_measured. Последнее — не цвет, а честное
    #: «эталона нет».
    light: str
    #: Расшифровка обязательна: цвет без слов возвращает к гаданию.
    reason: str
    required: int = 0
    missing: int = 0
    lapsed: int = 0
    expiring: int = 0


class SitePermitFactsRead(BaseSchema):
    """Действующие наряды-допуски площадки, разложенные по дисциплинам."""

    total: int = 0
    #: Дисциплина → число нарядов. Размечены только огневые и газоопасные
    #: работы: у остальных видов дисциплина из закона не следует.
    by_discipline: dict[str, int] = Field(default_factory=dict)
    without_discipline: int = 0
    #: Виды работ без дисциплины — названиями, чтобы «прочее» не было немым.
    without_discipline_titles: list[str] = Field(default_factory=list)
    #: ПОЧЕМУ у них нет дисциплины: иначе число читалось бы как недоделка.
    without_discipline_reason: str = ""


class SiteFactsRead(BaseSchema):
    """Факты площадки: то, что пересчитывается, а не оценивается."""

    workplaces: int = 0
    people: int = 0
    #: Люди КОМПАНИИ (не площадки) без рабочего места: они не отнесены ни к
    #: одной площадке и в светофор не попали. Число компании, а не площадки —
    #: у площадки таких людей быть не может по определению. Оно обязательно:
    #: иначе зелёная карточка означала бы «у площадки всё хорошо» там, где
    #: людей просто не разнесли по рабочим местам.
    people_without_workplace: int = 0
    permits: SitePermitFactsRead = Field(default_factory=SitePermitFactsRead)


class SiteNotCountedRead(BaseSchema):
    """Что к площадке привязано, но НЕ посчитано — с причиной, а не молчанием."""

    title: str
    reason: str


class SiteOverviewRead(BaseSchema):
    """Карточка площадки 360°: статус по всем дисциплинам на одном экране."""

    site_id: str
    name: str
    company_id: str
    address: str | None = None
    hazard_class: str | None = None
    #: Единственная дисциплина, чья ПРИМЕНИМОСТЬ следует из данных площадки.
    is_hazardous_production_facility: bool = False
    opo_register_number: str | None = None
    #: Итог по худшей ИЗМЕРЕННОЙ дисциплине; not_measured в итог не входит.
    overall: str
    disciplines: list[SiteDisciplineRead] = Field(default_factory=list)
    facts: SiteFactsRead = Field(default_factory=SiteFactsRead)
    not_counted: list[SiteNotCountedRead] = Field(default_factory=list)
