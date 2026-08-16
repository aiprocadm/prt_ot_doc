"""BIZ-51 срез-2 (Доп. №1 разд. 51.2): импорт как источник сигналов об изменениях.

Срез-1 дал ленту, которую заполняют руками. ТЗ перечисляет четыре источника
сигналов, и ручной ввод — лишь первый из них; второй — «импорт кадровых
изменений с diff „что изменилось с прошлого раза“». Здесь живут ПРАВИЛА этого
diff'а: чистые функции над фактами, без обращений к базе.

Почему чистые: правила решают судьбу ленты специалиста, и их надо уметь
проверить построчно, а не только через живой импорт файла на сто человек.
Всё, что требует базы (кто эта компания, был ли у неё кто-то раньше, как
зовут сотрудника), собирает сервисный слой и передаёт сюда готовым.

## Три решения, без которых лента врала бы

**1. Первичная загрузка НЕ порождает сигналов.** Когда аутсорсер впервые
привозит штатку клиента на 500 человек, это перенос данных, а не 500 приёмов
на работу. ТЗ говорит «diff — что изменилось с прошлого раза»; если прошлого
раза не было, diff'а не существует. Признак первичности считает сервис: были
ли у компании сотрудники ДО этой партии.

**2. Увольнение — по смене статуса, а не по исчезновению строки.** Соблазн
велик: кого нет в новом файле, тот уволен. Но файл почти никогда не полный —
выгружают один цех, одно подразделение, один филиал. По такому правилу
загрузка списка сварщиков «уволила» бы весь остальной завод, и лента выдала
бы сотни требований вернуть СИЗ у работающих людей. Поэтому увольнение
фиксируется только явным признаком: `employment_status` стал `terminated`.

**3. Перевод — это тот же вид, что увольнение.** В таблице разд. 51.1 строка
одна: «Уволен / переведён сотрудник», и последствия у них общие (закрыть
карточки, вернуть СИЗ, отозвать допуски). Разводить их на два вида значило бы
придумать девятый вид, которого в ТЗ нет.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.domains.managed_clients.change_feed import ClientChangeKind

__all__ = [
    "MAX_SIGNALS_PER_BATCH",
    "SIGNAL_TARGETS",
    "TERMINATED_STATUS",
    "ChangeSignal",
    "RowFact",
    "signals_for_batch",
]

#: Цели импорта, за которыми ТЗ закрепляет вид изменения. Остальные (нормы СИЗ
#: и то, что появится позже) сигналов не дают: в таблице разд. 51.1 для них
#: нет строки, а выдумывать последствия за ТЗ нельзя.
SIGNAL_TARGETS: frozenset[str] = frozenset({"persons", "positions", "sites"})

#: Значение ``EmploymentStatus.TERMINATED``. Строкой, а не импортом enum'а:
#: правила не должны тянуть за собой модели ради одной константы.
TERMINATED_STATUS = "terminated"

#: Потолок сигналов с одной партии. Загрузка на десять тысяч строк не должна
#: превращаться в ленту, которую физически нельзя прочитать: специалист увидит
#: первые и пометку «показаны не все», а полный список — в самой партии.
MAX_SIGNALS_PER_BATCH = 200


@dataclass(frozen=True)
class RowFact:
    """Факты об одной строке применённой партии — то, что собрал сервис.

    ``before`` — прежние значения изменённых полей (их хранит ``ImportRow``),
    ``now`` — текущее состояние записи. Обе стороны нужны именно потому, что
    ТЗ требует diff: «стало terminated» — это пара (было не terminated, стало
    terminated), и по одной стороне её не увидеть.
    """

    target: str
    action: str
    company_id: str | None
    title: str
    entity_id: str | None = None
    before: Mapping[str, Any] = field(default_factory=dict)
    now: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChangeSignal:
    """Предложение записать изменение в ленту клиента."""

    kind: ClientChangeKind
    company_id: str
    summary: str
    happened_on: date
    details: str | None = None
    entity_id: str | None = None


def _clean(value: Any) -> str:
    """Строка без пустот по краям; ``None`` и мусор — в пустую строку."""

    if value is None:
        return ""
    return str(value).strip()


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    text = _clean(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _summary(prefix: str, title: str, limit: int = 255) -> str:
    """«Принят: Иванов Иван» — с обрезкой под колонку ленты.

    Обрезается ХВОСТ, а не голова: вид изменения должен читаться с первого
    слова, даже если имя длинное.
    """

    text = f"{prefix}: {title}" if title else prefix
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _hire_date(fact: RowFact, applied_on: date) -> date:
    """Дата приёма из данных, иначе дата загрузки.

    Срез-1 закрепил: хранится дата САМОГО изменения, а не записи о нём. Если
    в файле есть дата приёма — сроки инструктажа и медосмотра считаются от
    неё, а не от того дня, когда специалист собрался загрузить файл.
    """

    return _as_date(fact.now.get("hired_at")) or applied_on


def _person_signal(fact: RowFact, applied_on: date) -> ChangeSignal | None:
    if fact.action == "create":
        return ChangeSignal(
            kind=ClientChangeKind.EMPLOYEE_HIRED,
            company_id=str(fact.company_id),
            summary=_summary("Принят", fact.title),
            happened_on=_hire_date(fact, applied_on),
            details="Замечено при загрузке кадровых данных.",
            entity_id=fact.entity_id,
        )

    if fact.action != "update":
        return None

    was_status = _clean(fact.before.get("employment_status")).lower()
    now_status = _clean(fact.now.get("employment_status")).lower()
    if now_status == TERMINATED_STATUS and was_status != TERMINATED_STATUS:
        return ChangeSignal(
            kind=ClientChangeKind.EMPLOYEE_LEFT,
            company_id=str(fact.company_id),
            summary=_summary("Уволен", fact.title),
            happened_on=applied_on,
            details="В загруженных данных статус стал «уволен».",
            entity_id=fact.entity_id,
        )

    # Перевод: сменилась должность. Сравниваем и код должности, и её название —
    # в файле может не быть ни справочного идентификатора, ни наоборот.
    for field_name in ("position_id", "position_title"):
        if field_name not in fact.before:
            continue
        was = _clean(fact.before.get(field_name))
        now = _clean(fact.now.get(field_name))
        if was == now:
            continue
        new_title = _clean(fact.now.get("position_title")) or now
        details = "Изменилась должность"
        if new_title:
            details = f"{details}: теперь «{new_title}»"
        return ChangeSignal(
            kind=ClientChangeKind.EMPLOYEE_LEFT,
            company_id=str(fact.company_id),
            summary=_summary("Переведён", fact.title),
            happened_on=applied_on,
            details=f"{details}.",
            entity_id=fact.entity_id,
        )

    return None


def _catalogue_signal(fact: RowFact, applied_on: date) -> ChangeSignal | None:
    """Новая должность или новый объект — только на создание.

    Переименование должности изменением у клиента не является: набор
    обязательств от смены буквы в названии не меняется, а лента, куда падает
    каждая правка опечатки, перестаёт читаться.
    """

    if fact.action != "create":
        return None
    if fact.target == "positions":
        return ChangeSignal(
            kind=ClientChangeKind.POSITION_ADDED,
            company_id=str(fact.company_id),
            summary=_summary("Новая должность", fact.title),
            happened_on=applied_on,
            details="Замечено при загрузке справочника должностей.",
            entity_id=fact.entity_id,
        )
    return ChangeSignal(
        kind=ClientChangeKind.SITE_ADDED,
        company_id=str(fact.company_id),
        summary=_summary("Новый объект", fact.title),
        happened_on=applied_on,
        details="Замечено при загрузке справочника объектов.",
        entity_id=fact.entity_id,
    )


def signals_for_batch(
    target: str,
    facts: Iterable[RowFact],
    *,
    applied_on: date,
    initial_load_companies: Iterable[str] = (),
    limit: int = MAX_SIGNALS_PER_BATCH,
) -> Sequence[ChangeSignal]:
    """Превратить строки применённой партии в предложения для ленты.

    ``initial_load_companies`` — компании, у которых до этой партии не было
    сотрудников. Для них сигналы не порождаются вовсе: это первый привоз
    данных, а не поток кадровых событий (см. решение 1 в docstring модуля).
    """

    if target not in SIGNAL_TARGETS:
        return ()

    skip = {str(cid) for cid in initial_load_companies if cid}
    out: list[ChangeSignal] = []
    for fact in facts:
        if not fact.company_id or str(fact.company_id) in skip:
            continue
        signal = (
            _person_signal(fact, applied_on)
            if target == "persons"
            else _catalogue_signal(fact, applied_on)
        )
        if signal is None:
            continue
        out.append(signal)
        if len(out) >= limit:
            break
    return tuple(out)
