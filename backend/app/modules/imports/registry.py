"""OPS-71 (разд. 71.1): реестр целей импорта — что вообще можно загружать.

Цель импорта описывается ДАННЫМИ, а не кодом: колонки, их типы, обязательность,
синонимы заголовков, справочные ссылки и естественный ключ. Из одного описания
получаются сразу три вещи, которые обязаны совпадать: пустой шаблон для скачивания,
автоопределение маппинга и правила валидации. Разъедься они — пользователь скачает
шаблон, заполнит его и получит ошибки на собственных колонках.

Добавление новой сущности к импорту = новая запись в ``IMPORT_TARGETS``, без единой
строки процедурного кода. Ровно этого требует разд. 71.1: «не разрозненные импортёры
под каждую сущность, а один фреймворк».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.master_data import Person, Position, Site
from app.models.ppe import PPENorm

__all__ = [
    "CREATABLE_LOOKUPS",
    "IMPORT_TARGETS",
    "ImportColumn",
    "ImportTarget",
    "NaturalKey",
    "get_target",
    "list_targets",
]


@dataclass(frozen=True)
class ImportColumn:
    """Одна колонка шаблона и её отображение в поле модели."""

    field: str
    title: str
    kind: str = "str"  # str | int | date | enum | bool
    required: bool = False
    # Синонимы заголовка для автоопределения маппинга. Сравнение нормализованное
    # (регистр, пробелы и пунктуация не важны) — см. planner.normalize_header.
    aliases: tuple[str, ...] = ()
    enum_values: tuple[str, ...] = ()
    # RU-синонимы значений перечисления: «уволен» → terminated.
    enum_aliases: dict[str, str] = field(default_factory=dict)
    max_length: int | None = None
    # Имя справочника (``company`` / ``position``): значение колонки — НАЗВАНИЕ,
    # а в поле модели ложится id найденной записи.
    lookup: str | None = None
    # Поле, значение которого входит в ключ справочника. Должность уникальна внутри
    # компании, поэтому одноимённые должности разных компаний не должны склеиться.
    lookup_scope_field: str | None = None
    # Можно ли заводить недостающую запись справочника прямо из импорта (разд. 71.3
    # «предложить создать или сопоставить»). Решается ПОЛЕМ, а не общим флагом:
    # должность — это по сути её название, а организация несёт реквизиты, и
    # автосоздание юрлица из опечатки в файле на 10 000 строк засорило бы справочник
    # так, что чистить пришлось бы руками.
    lookup_creatable: bool = False
    # Колонка нужна ТОЛЬКО для поиска и ключа, в модель она не пишется. Нормы СИЗ
    # висят на должности и организации не хранят, но найти должность без
    # организации нельзя: одноимённые должности разных юрлиц — разные записи.
    # Без этого флага значение уехало бы в конструктор модели как чужой аргумент.
    transient: bool = False
    # Дополнительно положить СЫРОЙ текст колонки в это поле. Карточка сотрудника
    # показывает свободнотекстовую должность, и терять её при сопоставлении со
    # справочником нельзя: пользователь увидит пустую строку там, где он что-то ввёл.
    also_set_raw: str | None = None


@dataclass(frozen=True)
class NaturalKey:
    """Вариант естественного ключа сущности (для идемпотентности и обновлений)."""

    fields: tuple[str, ...]
    title: str


@dataclass(frozen=True)
class ImportTarget:
    code: str
    title: str
    model: type[Any]
    columns: tuple[ImportColumn, ...]
    # Варианты ключа по убыванию надёжности: берётся ПЕРВЫЙ, у которого заполнены
    # все компоненты. Строка, не подходящая ни под один, отвергается — импорт без
    # ключа не идемпотентен, и повторная загрузка тихо наплодила бы дубли.
    natural_keys: tuple[NaturalKey, ...]
    description: str = ""

    def column(self, field_name: str) -> ImportColumn | None:
        for col in self.columns:
            if col.field == field_name:
                return col
        return None

    @property
    def key_fields(self) -> frozenset[str]:
        return frozenset(f for key in self.natural_keys for f in key.fields)


_COMPANY = ImportColumn(
    field="company_id",
    title="Организация",
    required=True,
    aliases=("организация", "компания", "юрлицо", "company", "organization"),
    lookup="company",
)


POSITIONS_TARGET = ImportTarget(
    code="positions",
    title="Должности (штатное расписание)",
    model=Position,
    description=(
        "Каталог должностей организации. Загружается ПЕРЕД сотрудниками: "
        "сотрудник ссылается на должность по названию."
    ),
    columns=(
        _COMPANY,
        ImportColumn(
            field="name",
            title="Должность",
            required=True,
            max_length=255,
            aliases=("должность", "наименование должности", "position", "job title"),
        ),
        ImportColumn(
            field="description",
            title="Описание",
            max_length=255,
            aliases=("описание", "комментарий", "description"),
        ),
        ImportColumn(
            field="safety_category",
            title="Категория по ОТ",
            max_length=64,
            aliases=("категория по от", "категория от", "safety category"),
        ),
        ImportColumn(
            field="working_conditions_class",
            title="Класс условий труда",
            max_length=32,
            aliases=("класс условий труда", "класс ут", "working conditions class"),
        ),
    ),
    natural_keys=(NaturalKey(fields=("company_id", "name"), title="организация + должность"),),
)


PERSONS_TARGET = ImportTarget(
    code="persons",
    title="Сотрудники",
    model=Person,
    description=(
        "Списки сотрудников — самый частый случай переезда (разд. 71.2). "
        "Ключ: табельный номер, иначе ФИО + дата рождения."
    ),
    columns=(
        _COMPANY,
        ImportColumn(
            field="last_name",
            title="Фамилия",
            required=True,
            max_length=100,
            aliases=("фамилия", "last name", "surname"),
        ),
        ImportColumn(
            field="first_name",
            title="Имя",
            required=True,
            max_length=100,
            aliases=("имя", "first name"),
        ),
        ImportColumn(
            field="middle_name",
            title="Отчество",
            max_length=100,
            aliases=("отчество", "middle name", "patronymic"),
        ),
        ImportColumn(
            field="birth_date",
            title="Дата рождения",
            kind="date",
            aliases=("дата рождения", "др", "birth date", "birthday"),
        ),
        ImportColumn(
            field="personnel_number",
            title="Табельный номер",
            max_length=32,
            aliases=("табельный номер", "табельный", "таб номер", "personnel number"),
        ),
        ImportColumn(
            field="position_id",
            title="Должность",
            aliases=("должность", "position", "job title"),
            lookup="position",
            lookup_scope_field="company_id",
            lookup_creatable=True,
            also_set_raw="position_title",
        ),
        ImportColumn(
            field="hired_at",
            title="Дата приёма",
            kind="date",
            aliases=("дата приёма", "дата приема", "принят", "hired at", "hire date"),
        ),
        ImportColumn(
            field="email",
            title="Email",
            max_length=320,
            aliases=("email", "почта", "e-mail", "электронная почта"),
        ),
        ImportColumn(
            field="phone",
            title="Телефон",
            max_length=32,
            aliases=("телефон", "phone", "тел"),
        ),
        ImportColumn(
            field="snils",
            title="СНИЛС",
            max_length=32,
            aliases=("снилс", "snils"),
        ),
        ImportColumn(
            field="employment_status",
            title="Статус",
            kind="enum",
            enum_values=("active", "on_leave", "suspended", "terminated"),
            enum_aliases={
                "работает": "active",
                "активен": "active",
                "в отпуске": "on_leave",
                "отпуск": "on_leave",
                "отстранён": "suspended",
                "отстранен": "suspended",
                "уволен": "terminated",
            },
            aliases=("статус", "статус занятости", "employment status"),
        ),
    ),
    natural_keys=(
        NaturalKey(
            fields=("company_id", "personnel_number"),
            title="организация + табельный номер",
        ),
        # Отчество в ключ НЕ входит: у части людей его нет, а требовать его
        # значило бы отвергать законные строки. Дата рождения обязательна —
        # без неё однофамильцы-тёзки слились бы в одну карточку.
        NaturalKey(
            fields=("company_id", "last_name", "first_name", "birth_date"),
            title="организация + ФИО + дата рождения",
        ),
    ),
)


SITES_TARGET = ImportTarget(
    code="sites",
    title="Объекты и площадки",
    model=Site,
    description="Производственные объекты организации: адрес, тип, контакты.",
    columns=(
        _COMPANY,
        ImportColumn(
            field="name",
            title="Объект",
            required=True,
            max_length=255,
            aliases=("объект", "площадка", "наименование объекта", "site"),
        ),
        ImportColumn(
            field="address",
            title="Адрес",
            max_length=255,
            aliases=("адрес", "address", "местонахождение"),
        ),
        ImportColumn(
            field="site_type",
            title="Тип объекта",
            max_length=64,
            aliases=("тип объекта", "тип", "site type"),
        ),
        ImportColumn(
            field="hazard_class",
            title="Класс опасности",
            max_length=32,
            aliases=("класс опасности", "hazard class"),
        ),
        ImportColumn(
            field="contact_name",
            title="Контактное лицо",
            max_length=255,
            aliases=("контактное лицо", "ответственный", "contact"),
        ),
        ImportColumn(
            field="contact_phone",
            title="Телефон",
            max_length=32,
            aliases=("телефон", "phone", "тел"),
        ),
    ),
    natural_keys=(NaturalKey(fields=("company_id", "name"), title="организация + объект"),),
)


PPE_NORMS_TARGET = ImportTarget(
    code="ppe_norms",
    title="Нормы выдачи СИЗ",
    model=PPENorm,
    description=(
        "Нормы СИЗ по должности и опасности (разд. 71.2, «мастера под частые "
        "структуры»). Должности и опасности должны существовать заранее."
    ),
    columns=(
        # Организация нужна, чтобы найти ДОЛЖНОСТЬ: одноимённые должности разных
        # юрлиц — разные записи. В самой норме организации нет, поэтому колонка
        # помечена transient и в модель не попадает.
        ImportColumn(
            field="company_id",
            title="Организация",
            required=True,
            aliases=("организация", "компания", "юрлицо"),
            lookup="company",
            transient=True,
        ),
        ImportColumn(
            field="position_id",
            title="Должность",
            required=True,
            aliases=("должность", "position"),
            lookup="position",
            lookup_scope_field="company_id",
            lookup_creatable=True,
        ),
        ImportColumn(
            field="hazard_id",
            title="Опасность",
            required=True,
            aliases=("опасность", "вредный фактор", "фактор", "hazard"),
            lookup="hazard",
        ),
        ImportColumn(
            field="item_name",
            title="Наименование СИЗ",
            required=True,
            max_length=255,
            aliases=("наименование сиз", "сиз", "средство защиты", "item"),
        ),
        ImportColumn(
            field="quantity",
            title="Количество",
            kind="int",
            aliases=("количество", "кол-во", "quantity", "норма выдачи"),
        ),
        ImportColumn(
            field="interval_days",
            title="Срок носки, дней",
            kind="int",
            aliases=("срок носки дней", "срок носки", "периодичность", "interval"),
        ),
    ),
    # Ровно уникальный ключ таблицы: повторная загрузка нормы обновляет её,
    # а не падает на UNIQUE(tenant, position, hazard, item_name).
    natural_keys=(
        NaturalKey(
            fields=("position_id", "hazard_id", "item_name"),
            title="должность + опасность + СИЗ",
        ),
    ),
)


IMPORT_TARGETS: dict[str, ImportTarget] = {
    POSITIONS_TARGET.code: POSITIONS_TARGET,
    PERSONS_TARGET.code: PERSONS_TARGET,
    SITES_TARGET.code: SITES_TARGET,
    PPE_NORMS_TARGET.code: PPE_NORMS_TARGET,
}


# Какие справочники вообще разрешено дозаводить из импорта — собирается из
# описаний колонок, чтобы список не пришлось поддерживать во втором месте.
CREATABLE_LOOKUPS: frozenset[str] = frozenset(
    column.lookup
    for target in IMPORT_TARGETS.values()
    for column in target.columns
    if column.lookup and column.lookup_creatable
)


def get_target(code: str) -> ImportTarget | None:
    return IMPORT_TARGETS.get(code)


def list_targets() -> list[ImportTarget]:
    return list(IMPORT_TARGETS.values())
