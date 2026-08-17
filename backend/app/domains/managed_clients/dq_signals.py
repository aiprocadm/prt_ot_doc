"""BIZ-51 срез-3 (Доп. №1 разд. 51.2): Data Quality как источник сигналов.

ТЗ перечисляет четыре источника сигналов ленты; третий — Data Quality Layer:
«выявляет неполноту/просрочку, которая тоже есть „изменение состояния“».
Правила просрочки в проекте давно есть (``app.modules.data_quality.rules``),
но их находки жили только в отчёте о качестве данных — до ленты сопровождения
они не доходили. Здесь живут ПРАВИЛА превращения находки в запись ленты:
чистые функции над фактами, без обращений к базе (тот же довод, что у
``import_signals``: судьбу ленты надо уметь проверить построчно).

## Три решения, без которых лента врала бы

**1. В ленту идёт только ПРОСРОЧКА.** Из шести типов находок Data Quality
изменением у клиента является один — «наступил срок» (медосмотр, обучение,
допуск, СИЗ): в таблице разд. 51.1 у него есть своя строка. Неполнота полей,
дубли и битые связи — дефекты ВЕДЕНИЯ УЧЁТА, а не события в компании клиента;
вид для них в закрытом списке ленты не предусмотрен, и выдумывать девятый вид
за ТЗ нельзя (то же решение, что с переводом в срезе-2). Они остаются в
отчёте качества данных — там их место.

**2. Дата изменения — день, когда истёк срок, а не день проверки.** Срез-1
закрепил: хранится дата САМОГО изменения. Специалист запустил сбор в
понедельник, а медосмотр истёк в пятницу — обязательства считаются с пятницы.

**3. Личность находки включает дату срока.** Проверка качества данных
запускается многократно, и та же просроченная запись не должна плодить
дубликаты (дубликаты хуже пропусков — срез-2). Но если ту же запись продлили
и срок истёк СНОВА — это новое событие, и лента обязана его показать. Поэтому
``source_ref`` строится из записи И даты истечения: тот же срок — та же
запись ленты, новый срок — новая.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from app.domains.managed_clients.change_feed import ClientChangeKind
from app.domains.managed_clients.import_signals import ChangeSignal

__all__ = [
    "EXPIRY_ENTITY_TITLES",
    "ExpiryFact",
    "signals_for_expiries",
    "source_ref_for",
]

#: Какие сущности несут просрочку и как они называются в ленте. Список закрыт
#: тем же доводом, что виды ленты: на каждую сущность у разд. 51.1 есть
#: последствия, а «прочее просроченное» без последствий — заметка, не сигнал.
EXPIRY_ENTITY_TITLES: dict[str, str] = {
    "medical_exam": "медосмотр",
    "training": "обучение",
    "permit": "допуск",
    "ppe_issue": "СИЗ",
}


@dataclass(frozen=True)
class ExpiryFact:
    """Факты об одной просроченной записи — то, что собрал сервис.

    ``expired_on`` обязателен не случайно: без даты истечения не построить ни
    дату изменения, ни личность находки, и такой факт правилами отбрасывается
    (сервис считает его отдельной строкой честного итога, а не молчит).
    """

    entity_type: str
    entity_id: str
    company_id: str | None
    person_title: str
    expired_on: date | None
    subject: str = ""


def source_ref_for(fact: ExpiryFact) -> str:
    """Личность находки: ``dq:<сущность>:<id записи>:<дата истечения>``.

    Дата в конце — решение 3 из docstring модуля: продлённая и снова
    просроченная запись даёт НОВУЮ личность и новую запись ленты.
    """

    expired = fact.expired_on.isoformat() if fact.expired_on else ""
    return f"dq:{fact.entity_type}:{fact.entity_id}:{expired}"


def _summary(fact: ExpiryFact, limit: int = 255) -> str:
    """«Просрочен медосмотр: Иванов Иван» — с обрезкой хвоста под колонку.

    Обрезается хвост, а не голова: вид изменения должен читаться с первого
    слова (правило среза-2).
    """

    noun = EXPIRY_ENTITY_TITLES[fact.entity_type]
    prefix = {
        "medical_exam": f"Просрочен {noun}",
        "training": f"Просрочено {noun}",
        "permit": f"Просрочен {noun}",
        "ppe_issue": f"Просрочены {noun}",
    }[fact.entity_type]
    text = f"{prefix}: {fact.person_title}" if fact.person_title else prefix
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _details(fact: ExpiryFact) -> str:
    parts = ["Найдено проверкой качества данных."]
    if fact.expired_on is not None:
        parts.append(f"Срок истёк {fact.expired_on.strftime('%d.%m.%Y')}.")
    if fact.subject:
        parts.append(f"Предмет: {fact.subject}.")
    return " ".join(parts)


def signals_for_expiries(facts: Iterable[ExpiryFact]) -> Sequence[ChangeSignal]:
    """Превратить просрочки в предложения для ленты.

    Вид у всех один — «Наступает срок»: это строка таблицы разд. 51.1
    «Наступление срока (обучение/медосмотр/СИЗ/проверка)», и именно её
    подсказки (задача на продление, генерация комплекта) здесь уместны.

    Потолок записей НЕ здесь: сервис сначала выбрасывает уже записанное и
    ограничивает только НОВОЕ — иначе прогон по арендатору с тремя сотнями
    старых просрочек никогда не дошёл бы до свежих.
    """

    out: list[ChangeSignal] = []
    for fact in facts:
        if fact.entity_type not in EXPIRY_ENTITY_TITLES:
            continue
        if not fact.company_id or fact.expired_on is None:
            continue
        out.append(
            ChangeSignal(
                kind=ClientChangeKind.DEADLINE_APPROACHING,
                company_id=str(fact.company_id),
                summary=_summary(fact),
                happened_on=fact.expired_on,
                details=_details(fact),
                entity_id=fact.entity_id,
                source_ref=source_ref_for(fact),
            )
        )
    return tuple(out)
