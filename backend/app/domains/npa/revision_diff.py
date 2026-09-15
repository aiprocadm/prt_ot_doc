"""Сравнение двух редакций акта по пунктам (B.18 разд. 19.4, срез-202).

ЗАЧЕМ. Разд. 19.4 требует процесс «черновик → публикация → ДИФФ → уведомления
→ задачи на пересмотр → контроль завершения». Всё, кроме диффа, уже есть
(срезы 141, 144, 198). Диффа не было, потому что сравнивать было нечего: у
редакции не хранился текст.

ГЛАВНОЕ РЕШЕНИЕ МОДУЛЯ — «ТЕКСТА НЕТ» И «ИЗМЕНЕНИЙ НЕТ» ЭТО РАЗНЫЕ ОТВЕТЫ.

Это тот же класс вранья, что срез-197 вылавливал у сводки влияния: отсутствие
строки читалось как «этот закон их не задевает». Здесь соблазн ещё сильнее —
пустой снимок легко сравнить с пустым и получить «изменений нет», а пустой с
полным — «всё добавлено». Оба ответа выглядят как работа и оба ложь: у редакций,
заведённых до этого среза, текста нет ВООБЩЕ, и сказать про них можно ровно
одно — «текст этой редакции в систему не заносили».

СЛОВАРЬ ИЗМЕНЕНИЙ ВЗЯТ У СРАВНЕНИЯ ВЕРСИЙ ДОКУМЕНТА
(``app.services.document_insights.diff_version_data_json``): ``added`` /
``removed`` / ``modified``. Заводить второй словарь для того же понятия значило
бы, что «изменено» в одном месте продукта и в другом — разные слова для
человека, который читает оба экрана.

ЗАПУСК проверок: ``PYTHONPATH=backend pytest tests/test_npa_revision_diff.py -v``.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CHANGE_TITLES",
    "ClauseChange",
    "NO_TEXT_REASON",
    "RevisionDiff",
    "diff_clauses",
    "normalize_text",
]

ADDED = "added"
REMOVED = "removed"
MODIFIED = "modified"
UNCHANGED = "unchanged"

#: Подписи словами приходят с сервера: витрина не должна знать, что "modified"
#: значит «текст изменён». Это то самое место, где экраны раз за разом печатали
#: служебный код вместо человеческого текста.
CHANGE_TITLES: dict[str, str] = {
    ADDED: "Пункт добавлен",
    REMOVED: "Пункт исключён",
    MODIFIED: "Текст изменён",
    UNCHANGED: "Без изменений",
}

#: Причина отказа словами. Отдаётся ВМЕСТО списка изменений, а не рядом с
#: пустым списком: пустой список означал бы «сравнили и ничего не нашли».
NO_TEXT_REASON = "Текст этой редакции в систему не заносили — сравнивать не с чем"


def normalize_text(value: str) -> str:
    """Текст для СРАВНЕНИЯ, не для показа.

    Пункт, перенесённый в систему второй раз, часто отличается только мягкими
    переносами и двойными пробелами после вставки из документа. Показывать
    такую разницу человеку как «текст изменён» — значит утопить настоящие
    правки в шуме, и на третий раз он перестанет открывать дифф вовсе.

    Поэтому сравниваются схлопнутые пробелы, а ПОКАЗЫВАЕТСЯ всегда исходный
    текст — обрезать пользовательские данные при показе нельзя.
    """

    return " ".join(value.split())


@dataclass(frozen=True, slots=True)
class ClauseChange:
    """Одно изменение. ``before``/``after`` — ИСХОДНЫЕ тексты, не схлопнутые."""

    code: str
    change: str
    before: str | None
    after: str | None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "code": self.code,
            "change": self.change,
            "change_title": CHANGE_TITLES[self.change],
            "before": self.before,
            "after": self.after,
        }


@dataclass(frozen=True, slots=True)
class RevisionDiff:
    """Итог сравнения. ``comparable=False`` — ответ «не можем», а не «пусто»."""

    comparable: bool
    reason: str
    changes: tuple[ClauseChange, ...]
    unchanged: int

    def as_dict(self) -> dict[str, object]:
        return {
            "comparable": self.comparable,
            "reason": self.reason,
            "changes": [change.as_dict() for change in self.changes],
            "summary": {
                ADDED: sum(1 for c in self.changes if c.change == ADDED),
                REMOVED: sum(1 for c in self.changes if c.change == REMOVED),
                MODIFIED: sum(1 for c in self.changes if c.change == MODIFIED),
                UNCHANGED: self.unchanged,
            },
        }


def diff_clauses(
    before: dict[str, str] | None,
    after: dict[str, str] | None,
) -> RevisionDiff:
    """Сравнить два набора пунктов ``{код: текст}``.

    ``None`` означает «снимка нет» и НЕ равно пустому словарю: пустой набор —
    это осознанно заведённая редакция без пунктов (бывает у актов, где текст
    ведут одним документом), а ``None`` — измерение, которого не делали.

    Пункты сопоставляются ПО КОДУ, а не по порядку. Порядок в нормативном акте
    не несёт смысла сам по себе, а коды («п. 4», «ст. 12 ч. 2») — несут: они и
    есть то, на что ссылается требование.
    """

    if before is None or after is None:
        return RevisionDiff(comparable=False, reason=NO_TEXT_REASON, changes=(), unchanged=0)

    changes: list[ClauseChange] = []
    unchanged = 0
    # Порядок вывода — по коду пункта: дифф читают сверху вниз рядом с текстом
    # акта, и прыгающий порядок заставил бы искать глазами.
    for code in sorted(set(before) | set(after)):
        old = before.get(code)
        new = after.get(code)
        if old is None:
            changes.append(ClauseChange(code=code, change=ADDED, before=None, after=new))
        elif new is None:
            changes.append(ClauseChange(code=code, change=REMOVED, before=old, after=None))
        elif normalize_text(old) != normalize_text(new):
            changes.append(ClauseChange(code=code, change=MODIFIED, before=old, after=new))
        else:
            unchanged += 1
    return RevisionDiff(comparable=True, reason="", changes=tuple(changes), unchanged=unchanged)
