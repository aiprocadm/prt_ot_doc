"""OPS-71 срез-8 (разд. 71.2): профили типовых источников.

ТЗ: «Готовые сценарии переезда снижают барьер входа — это прямой инструмент
продаж»: выгрузка 1С, типовые Excel-структуры, форматы конкурентов.

Профиль — это ЗНАНИЕ О ЧУЖОМ ФАЙЛЕ: как называются его колонки и что с ними
сделать, чтобы получилась наша сущность. Он не заменяет цель импорта, а
подставляет к ней готовое сопоставление, которое иначе пользователь собирал бы
руками при каждой загрузке.

**Разбор «ФИО» одной колонкой — не украшение, а условие применимости.** В
выгрузке 1С фамилия, имя и отчество лежат в ОДНОЙ ячейке, а у нас это три поля.
Без разбора профиль для 1С был бы бесполезен: сопоставить одну колонку с тремя
полями невозможно, и пользователю пришлось бы править файл до загрузки — ровно
та работа, которую профиль и должен снимать.

Автоопределение профиля по заголовкам намеренно требовательное: профиль меняет
трактовку колонок, и ошибиться здесь дороже, чем не угадать.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.modules.imports.planner import normalize_header

__all__ = [
    "IMPORT_PROFILES",
    "ImportProfile",
    "apply_profile_splits",
    "detect_profile",
    "get_profile",
    "list_profiles",
]


@dataclass(frozen=True)
class ColumnSplit:
    """Разбор одной колонки источника на несколько наших колонок."""

    source: str
    # Куда раскладываются части — по порядку. Лишние части склеиваются в последнюю
    # названную колонку: двойная фамилия «Иванов-Петров Иван Сергеевич» не должна
    # превращать отчество в мусор.
    parts: tuple[str, ...]


@dataclass(frozen=True)
class ImportProfile:
    code: str
    title: str
    target: str
    source: str  # 1c | excel | competitor
    description: str = ""
    # Готовое сопоставление «поле модели → заголовок В ФАЙЛЕ ИСТОЧНИКА».
    mapping: dict[str, str] = field(default_factory=dict)
    splits: tuple[ColumnSplit, ...] = ()
    # Заголовки, по которым файл опознаётся как этот источник. Требуются ВСЕ:
    # профиль меняет трактовку колонок, и ошибиться дороже, чем не угадать.
    signature: tuple[str, ...] = ()


ZUP_PERSONS = ImportProfile(
    code="1c_zup_persons",
    title="1С:ЗУП — список сотрудников",
    target="persons",
    source="1c",
    description=(
        "Типовая выгрузка сотрудников из 1С:ЗУП: ФИО одной колонкой, "
        "табельный номер, подразделение и должность."
    ),
    mapping={
        "company_id": "Организация",
        "personnel_number": "Табельный номер",
        "position_id": "Должность",
        "hired_at": "Дата приема",
        "birth_date": "Дата рождения",
    },
    splits=(ColumnSplit(source="ФИО", parts=("last_name", "first_name", "middle_name")),),
    signature=("ФИО", "Табельный номер"),
)


EXCEL_STAFF_LIST = ImportProfile(
    code="excel_staff_list",
    title="Excel — штатное расписание (должности)",
    target="positions",
    source="excel",
    description="Частая ручная таблица: организация, должность, категория по ОТ.",
    mapping={
        "company_id": "Организация",
        "name": "Наименование должности",
        "safety_category": "Категория по ОТ",
    },
    signature=("Наименование должности",),
)


EXCEL_PERSONS_FIO = ImportProfile(
    code="excel_persons_fio",
    title="Excel — список работников (ФИО одной колонкой)",
    target="persons",
    source="excel",
    description="Ручная таблица кадровика: ФИО в одной ячейке, должность текстом.",
    mapping={
        "company_id": "Организация",
        "position_id": "Должность",
        "birth_date": "Дата рождения",
    },
    splits=(ColumnSplit(source="ФИО", parts=("last_name", "first_name", "middle_name")),),
    signature=("ФИО",),
)


IMPORT_PROFILES: dict[str, ImportProfile] = {
    p.code: p for p in (ZUP_PERSONS, EXCEL_PERSONS_FIO, EXCEL_STAFF_LIST)
}


def get_profile(code: str) -> ImportProfile | None:
    return IMPORT_PROFILES.get(code)


def list_profiles(target: str | None = None) -> list[ImportProfile]:
    profiles = list(IMPORT_PROFILES.values())
    if target:
        profiles = [p for p in profiles if p.target == target]
    return profiles


def detect_profile(target: str, headers: list[str]) -> ImportProfile | None:
    """Опознать источник по заголовкам файла.

    Требуются ВСЕ подписи профиля. Из подходящих берётся самый требовательный
    (с наибольшим числом подписей): «1С:ЗУП» специфичнее, чем «Excel с ФИО»,
    и предлагать надо его.
    """

    present = {normalize_header(h) for h in headers}
    matched = [
        profile
        for profile in list_profiles(target)
        if profile.signature and all(normalize_header(sig) in present for sig in profile.signature)
    ]
    if not matched:
        return None
    return max(matched, key=lambda p: len(p.signature))


_SPACES = re.compile(r"\s+")


def apply_profile_splits(profile: ImportProfile, rows: list[dict[str, object]]) -> list[str]:
    """Разложить составные колонки источника. Возвращает добавленные заголовки.

    Строки правятся НА МЕСТЕ: разбор — это нормализация источника, и делать её
    надо один раз, до маппинга, а не в каждом правиле валидации.
    """

    added: list[str] = []
    for split in profile.splits:
        for row in rows:
            raw = None
            for key, value in row.items():
                if normalize_header(key) == normalize_header(split.source):
                    raw = value
                    break
            if raw is None:
                continue
            pieces = [p for p in _SPACES.split(str(raw).strip()) if p]
            if not pieces:
                continue
            for index, part_name in enumerate(split.parts):
                if index >= len(pieces):
                    break
                # Последняя названная часть забирает весь остаток: у «Иванов Иван
                # Сергеевич Оглы» отчество из двух слов, и терять хвост нельзя.
                is_last = index == len(split.parts) - 1
                row[part_name] = " ".join(pieces[index:]) if is_last else pieces[index]
        added.extend(split.parts)
    return added


def profile_overrides(profile: ImportProfile) -> dict[str, str]:
    """Сопоставление профиля + колонки, полученные разбором (они уже наши)."""

    overrides = dict(profile.mapping)
    for split in profile.splits:
        for part in split.parts:
            overrides[part] = part
    return overrides
