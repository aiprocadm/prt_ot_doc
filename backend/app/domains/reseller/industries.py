"""Отраслевые наборы для нового арендатора (BIZ-52 срез-12, Доп. №1 разд. 52.3).

Срез-7 научил применять эталонный набор — но набор был ОДИН на всех
(`default`, плюс `demo` для показа). ТЗ просит отраслевые: строительство,
производство, транспорт, энергетика. Разница не косметическая: у стройки и у
транспортной компании расходятся и должности, и опасности, и меры — клиент,
получивший общий набор, всё равно заводит своё вручную, то есть тиражирование
не срабатывает ровно там, где обещано.

**Отрасль — не тип в базе.** Список закрыт ЗДЕСЬ, а хранится строкой: заводить
native enum ради ярлыка значит платить миграцией типа за каждую новую отрасль
(урок BIZ-50 среза-2, где по той же причине не расширяли `documentpackmodule`).

**Наполнение — заготовка, а не нормативный перечень.** Набор экономит первые
часы работы и заведомо правится клиентом; выдавать его за исчерпывающий список
опасностей отрасли было бы опасной неправдой.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Общий набор. Тот же файл, что применялся всем до этого среза, — поэтому
#: поведение без указания отрасли не меняется ни на строку.
DEFAULT_INDUSTRY = "general"

#: Показательный набор для демонстраций. Живёт отдельно от отраслей: его
#: выбирает флаг `demo_data`, а не человек из списка.
DEMO_PACK = "demo"


@dataclass(frozen=True)
class Industry:
    """Отрасль и файл её набора."""

    code: str
    title: str
    #: Имя файла набора без расширения в `seed/tenant_starter_packs/v1/`.
    pack: str


#: Закрытый список. Порядок — порядок показа в интерфейсе: общий первым, потому
#: что он подходит любому, остальные по алфавиту.
INDUSTRIES: tuple[Industry, ...] = (
    Industry(DEFAULT_INDUSTRY, "Общая (подходит любой организации)", "default"),
    Industry("construction", "Строительство", "construction"),
    Industry("energy", "Энергетика", "energy"),
    Industry("manufacturing", "Производство", "manufacturing"),
    Industry("transport", "Транспорт", "transport"),
)

INDUSTRY_CODES: frozenset[str] = frozenset(item.code for item in INDUSTRIES)

_BY_CODE: dict[str, Industry] = {item.code: item for item in INDUSTRIES}


class UnknownIndustryError(ValueError):
    """Отрасль вне списка.

    Отдельная ошибка, а не тихий откат на общий набор: партнёр, ошибившийся в
    коде отрасли, иначе решил бы, что завёл клиенту стройку, а получил бы общий
    набор — и узнал бы об этом от самого клиента.
    """

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Неизвестная отрасль: {code}")


def resolve_industry(code: str | None) -> Industry:
    """Отрасль по коду. Пусто — общая."""

    if code is None or not code.strip():
        return _BY_CODE[DEFAULT_INDUSTRY]
    normalized = code.strip().lower()
    if normalized not in _BY_CODE:
        raise UnknownIndustryError(code)
    return _BY_CODE[normalized]


def pack_name_for(*, industry: str | None, demo: bool) -> str:
    """Имя файла набора для выдачи арендатора.

    Демонстрационный набор перекрывает отрасль: он существует ради показа
    заполненной системы, и «демо в отрасли строительство» означало бы третий
    вид набора на каждую отрасль — набор файлов вырос бы вчетверо ради
    сценария, которого никто не просил.

    Отрасль при этом ПРОВЕРЯЕТСЯ даже с флагом демо: опечатка не должна
    оставаться незамеченной только потому, что в этот раз она ни на что не
    повлияла.
    """

    resolved = resolve_industry(industry)
    return DEMO_PACK if demo else resolved.pack
