"""Перенос конфигурации арендатора (BIZ-52 срез-16, Доп. №1 разд. 52.3).

ТЗ называет тиражирование «главной технической ценностью для продажи». Срезы 7 и
12 научили РАЗВОРАЧИВАТЬ клиента с наполнением — из файла эталона. Обратной
дороги не было: партнёр, донастроивший клиента под свою практику, не мог снять с
него слепок и повторить на следующем. Каждый новый клиент донастраивался руками
заново.

**Формат выгрузки — тот же, что у эталонного набора.** Второй формат означал бы
два разбора, два набора правил и однажды — расхождение между «что можно
применить при выдаче» и «что можно перенести». А так выгрузка настроенного
клиента годится файлом эталона: положил в `seed/tenant_starter_packs/v1/` — и
это отраслевой набор.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domains.reseller.starter_pack import plan_starter_pack

#: Версия формата. Совпадает с каталогом эталонов `v1`: выгрузка обязана быть
#: применимой тем же кодом, что и файл из репозитория.
CONFIG_FORMAT_VERSION = "v1"


@dataclass(frozen=True)
class TenantConfig:
    """Снимок настроек арендатора в формате эталонного набора."""

    #: Справочники: вид → названия в порядке создания.
    reference_data: dict[str, list[str]] = field(default_factory=dict)
    #: Слаг источника. Не для применения — для человека, который через месяц
    #: спросит «откуда этот файл».
    source_slug: str | None = None

    def as_payload(self, *, pack: str) -> dict:
        return {
            "version": CONFIG_FORMAT_VERSION,
            "pack": pack,
            # Выгрузка снята с живого клиента, поэтому и применима к клиентам.
            "enabled_for": ["customer", "pilot"],
            "exported_from": self.source_slug,
            "reference_data": dict(self.reference_data),
        }


def build_config(
    *, positions: list[str], hazards: list[str], controls: list[str], source_slug: str
) -> TenantConfig:
    """Собрать снимок из справочников арендатора.

    Пустые виды в выгрузку НЕ попадают: `"hazards": []` в файле читается как
    «опасностей нет», а правда — «их не завели». Отсутствие ключа честнее.
    """

    reference: dict[str, list[str]] = {}
    for kind, values in (
        ("positions", positions),
        ("hazards", hazards),
        ("controls", controls),
    ):
        cleaned = _dedupe(values)
        if cleaned:
            reference[kind] = cleaned
    return TenantConfig(reference_data=reference, source_slug=source_slug)


def _dedupe(values: list[str]) -> list[str]:
    """Убрать пустые и повторы без учёта регистра, сохранив порядок.

    Порядок — тот, в котором строки завёл человек: он несёт смысл (сначала
    частое, потом редкое), и сортировка по алфавиту его потеряла бы.
    """

    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = " ".join(str(value or "").split())
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


@dataclass(frozen=True)
class ConfigCheck:
    """Что в присланном файле применимо, а что нет."""

    applicable: dict[str, list[str]]
    #: Виды, которые не ложатся в таблицы, — с причиной.
    skipped: list[str]
    #: Незнакомые ключи: файл мог уйти вперёд кода, это надо заметить.
    unknown: list[str]

    @property
    def is_empty(self) -> bool:
        return not any(self.applicable.values())


def check_config(payload: dict) -> ConfigCheck:
    """Разобрать присланный файл до применения.

    Отдельно от применения намеренно: человек должен увидеть, ЧТО именно
    появится у клиента, до того как оно появится. Перенос «вслепую» на чужой
    арендатор — не та операция, которую делают на ощупь.

    Классификация видов НЕ СВОЯ, а из `plan_starter_pack` (срез-7). Первая
    версия этого модуля делила виды сама — и разошлась на первом же файле:
    в `demo.json` часть ключей задана ЧИСЛАМИ («сколько демо-записей создать»),
    а своя проверка «это не список — значит незнакомый ключ» объявляла их
    ошибкой. Одна правда о применимом; две уже разъехались.
    """

    plan = plan_starter_pack(payload)
    applicable = {
        kind: _dedupe([str(item) for item in values])
        for kind, values in plan.apply.items()
        if values
    }
    return ConfigCheck(
        applicable={kind: values for kind, values in applicable.items() if values},
        skipped=sorted(plan.skipped),
        unknown=list(plan.unknown),
    )
