"""Профили импорта, которые арендатор заводит из СВОЕГО файла (OPS-71, разд. 71.2).

ЧТО БЫЛО. Профили источников лежали константами в коде, и остаток строки звучал
так: «профили конкурентов (нужны образцы их выгрузок — вопрос владельцу)».
Поддержка каждого нового формата упиралась сразу в две вещи: достать чужой файл
и написать под него код. Обе — вне досягаемости того, кто прямо сейчас
переезжает.

РЕШЕНИЕ (2026-09-14, делегировано владельцем). Образцы конкурентов НЕ НУЖНЫ. У
клиента, который переезжает, его собственная выгрузка уже есть. Он один раз
сопоставляет колонки руками — и сохраняет это сопоставление профилем. Дальше
файл той же формы опознаётся сам.

Система учится у того, у кого файл ДЕЙСТВИТЕЛЬНО есть, вместо того чтобы ждать,
пока кто-то раздобудет образец.

ПОЧЕМУ ПОДПИСЬ СЧИТАЕТСЯ АВТОМАТИЧЕСКИ. Просить человека вручную выбрать
«заголовки, по которым узнавать файл» значит задать вопрос, на который он не
знает ответа. Подпись выводится из тех заголовков, которые он СОПОСТАВИЛ: раз
он их выбрал, они в файле есть и важны.

ПОЧЕМУ СВОЙ ПРОФИЛЬ СИЛЬНЕЕ ВСТРОЕННОГО. Арендатор знает свою прошлую систему
лучше, чем догадка платформы: если он завёл профиль под свой файл, подставлять
вместо него встроенный значило бы спорить с человеком о его собственных данных.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.imports.planner import normalize_header
from app.modules.imports.profiles import ColumnSplit, ImportProfile

#: Сколько заголовков берём в подпись. Одного мало — совпадёт со всем подряд;
#: все подряд — и профиль перестанет узнавать файл, в котором добавили колонку.
SIGNATURE_SIZE = 4

#: Код профиля: латиница, цифры, дефис и подчёркивание. Из заголовка кириллицей
#: код не собрать, поэтому он либо задан, либо строится из порядкового номера.
_CODE_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

#: Отметка, по которой в перечне видно, что профиль заведён арендатором, а не
#: поставляется платформой. Без неё человек не отличит своё от чужого.
TENANT_SOURCE = "tenant"


class SavedProfileError(ValueError):
    """Профиль нельзя сохранить. Сообщение предназначено человеку."""


@dataclass(frozen=True)
class ProfileDraft:
    """То, что пришло от человека после ручного сопоставления."""

    code: str
    title: str
    target: str
    mapping: dict[str, str]
    splits: dict[str, list[str]]
    description: str = ""


def build_signature(mapping: dict[str, str], *, size: int = SIGNATURE_SIZE) -> list[str]:
    """Подпись файла из сопоставленных заголовков.

    Берутся заголовки ИСТОЧНИКА (значения сопоставления), а не имена наших
    полей: узнаём мы чужой файл, а не свою модель.

    Порядок устойчивый (по алфавиту нормализованных): иначе одно и то же
    сопоставление давало бы разные подписи от запуска к запуску, и профиль
    переставал бы совпадать сам с собой.
    """

    headers = sorted({normalize_header(v) for v in mapping.values() if str(v).strip()})
    return headers[:size]


def validate_draft(draft: ProfileDraft, *, known_targets: set[str]) -> None:
    """Проверить черновик до записи в базу."""

    if not _CODE_RE.match(draft.code or ""):
        raise SavedProfileError(
            "Код профиля: латинские буквы, цифры, дефис или подчёркивание, до 64 знаков"
        )
    if not (draft.title or "").strip():
        raise SavedProfileError("У профиля должно быть название — его выбирают из списка")
    if draft.target not in known_targets:
        raise SavedProfileError(
            f"Неизвестная цель импорта: {draft.target!r}. Известные: "
            f"{', '.join(sorted(known_targets))}"
        )
    if not draft.mapping:
        raise SavedProfileError(
            "Профиль без сопоставления колонок бесполезен: он не подставит ничего"
        )
    for field_name, header in draft.mapping.items():
        if not str(header).strip():
            raise SavedProfileError(f"У поля «{field_name}» не выбран заголовок из файла")

    # Разбор составной колонки обязан ссылаться на существующий заголовок:
    # иначе он молча не сработает, и человек получит пустые фамилию и имя.
    known_headers = {normalize_header(v) for v in draft.mapping.values()}
    for source, parts in (draft.splits or {}).items():
        if normalize_header(source) not in known_headers:
            raise SavedProfileError(
                f"Разбор колонки «{source}» ссылается на заголовок, которого нет в "
                "сопоставлении: разбор молча не сработал бы"
            )
        if len(parts or []) < 2:
            raise SavedProfileError(f"Разбор колонки «{source}» должен называть минимум две части")


def to_import_profile(row) -> ImportProfile:
    """Строка базы → профиль в том же виде, что и встроенные.

    Один тип для своих и встроенных профилей — чтобы опознание, подстановка и
    разбор не знали, откуда профиль взялся. Две ветки кода здесь однажды
    разошлись бы в поведении.
    """

    splits = tuple(
        ColumnSplit(source=source, parts=tuple(parts))
        for source, parts in (row.splits or {}).items()
        if parts
    )
    return ImportProfile(
        code=row.code,
        title=row.title,
        target=row.target,
        source=TENANT_SOURCE,
        description=row.description or "",
        mapping=dict(row.mapping or {}),
        splits=splits,
        signature=tuple(row.signature or []),
    )


def merge_profiles(builtin: list[ImportProfile], saved: list[ImportProfile]) -> list[ImportProfile]:
    """Перечень профилей: свои ВПЕРЕДИ и сильнее одноимённых встроенных.

    Арендатор знает свою прошлую систему лучше, чем догадка платформы.
    """

    own_codes = {profile.code for profile in saved}
    return [*saved, *(p for p in builtin if p.code not in own_codes)]


def detect(profiles: list[ImportProfile], headers: list[str]) -> ImportProfile | None:
    """Опознать файл. Правила те же, что у встроенных: требуются ВСЕ подписи.

    Из подходящих берётся самый требовательный; при равенстве — профиль
    арендатора: спорить с человеком о его собственном файле нельзя.
    """

    present = {normalize_header(h) for h in headers}
    matched = [
        profile
        for profile in profiles
        if profile.signature and all(normalize_header(s) in present for s in profile.signature)
    ]
    if not matched:
        return None
    return max(
        matched,
        key=lambda p: (len(p.signature), p.source == TENANT_SOURCE),
    )


__all__ = [
    "SIGNATURE_SIZE",
    "TENANT_SOURCE",
    "ProfileDraft",
    "SavedProfileError",
    "build_signature",
    "detect",
    "merge_profiles",
    "to_import_profile",
    "validate_draft",
]
