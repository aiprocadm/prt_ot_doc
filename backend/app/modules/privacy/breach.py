"""Порядок при утечке персональных данных (152-ФЗ, разд. 66.3, срез-207).

ЧТО НАШЛА СВЕРКА. Критерии приёмки 70.1 по ПДн («экспорт/удаление субъекта
работает, журнал доступа ведётся») выполнены. Но поимённый разбор разд. 66
показал незакрытый пункт 66.3: «Порядок при утечке: уведомление Роскомнадзора и
субъектов **в установленные сроки** — процедура incident response».

В продукте этого не было ВООБЩЕ. Происшествия (``IncidentType``) — про охрану
труда: несчастный случай, микротравма, «почти случилось», опасное условие. Утечки
персональных данных среди них нет, а значит, у организации не было ни места, где
про неё записать, ни срока, который кто-то считает.

## Сроки взяты из закона, а не придуманы

152-ФЗ (в редакции с 2022 года) даёт оператору два срока, и оба — **в часах от
момента ОБНАРУЖЕНИЯ**, а не от момента самой утечки:

* **24 часа** — уведомить Роскомнадзор о случившемся;
* **72 часа** — сообщить результаты внутреннего расследования.

Часы, а не дни: срок с временем нельзя округлять до даты — округление тихо
дарит или отнимает часы там, где счёт идёт на часы.

## Три решения, которые важнее кода

**1. Платформа НИЧЕГО НЕ ОТПРАВЛЯЕТ в Роскомнадзор, и это сказано прямо.**
Канала для такой отправки не существует — уведомление подают через форму
регулятора. Кнопка «уведомить», которая на самом деле только ставит галочку,
была бы худшим из возможных: человек решит, что дело сделано. Здесь ведётся
ОБЯЗАТЕЛЬСТВО С ВЫЧИСЛИМЫМ СРОКОМ, а факт отправки отмечает человек. Тот же
приём, что в срезе-188 у удаления из резервных копий.

**2. Уведомить регулятора и уведомить людей — ДВА РАЗНЫХ обязательства.**
Закон требует обоих, и выполняются они по-разному и в разное время. Одна
галочка на оба означала бы, что выполнив лёгкое, организация считает закрытым и
трудное.

**НЕ ПУТАТЬ С `PdnAgreementCreate.breach_notification_hours`.** То поле — срок
из ДОГОВОРА ПОРУЧЕНИЯ: за сколько часов обработчик обязан сообщить оператору.
Здесь — сроки ЗАКОНА, за которые оператор обязан сообщить регулятору и людям.
Обязательства разные, стороны разные, и слить их в одно значило бы, что
договорённость двух компаний подменяет требование закона.

**3. Момент обнаружения вводит человек.** Платформа не может его знать: утечку
замечают письмом, звонком, сообщением в чате. Подставить сюда «сейчас» значило
бы подсунуть правдоподобное значение вместо измерения — и сдвинуть срок на
столько, сколько прошло до записи.

ЗАПУСК проверок: ``PYTHONPATH=backend pytest tests/test_privacy_breach.py -v``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

__all__ = [
    "BREACH_STAGES",
    "NOTIFY_REGULATOR_HOURS",
    "REPORT_FINDINGS_HOURS",
    "STAGE_TITLES",
    "BreachDeadline",
    "deadlines_for",
]

#: Срок уведомления Роскомнадзора о самом факте — 24 часа от ОБНАРУЖЕНИЯ.
NOTIFY_REGULATOR_HOURS = 24
#: Срок сообщения о результатах внутреннего расследования — 72 часа.
REPORT_FINDINGS_HOURS = 72

#: Этап — код для ветвления, подпись — для человека.
STAGE_NOTIFY = "notify_regulator"
STAGE_FINDINGS = "report_findings"
STAGE_SUBJECTS = "notify_subjects"

BREACH_STAGES: tuple[str, ...] = (STAGE_NOTIFY, STAGE_FINDINGS, STAGE_SUBJECTS)

STAGE_TITLES: dict[str, str] = {
    STAGE_NOTIFY: "Уведомить Роскомнадзор о факте утечки",
    STAGE_FINDINGS: "Сообщить результаты внутреннего расследования",
    # У этого обязательства нет срока в часах: закон требует уведомить
    # субъектов, но момент определяется обстоятельствами. Пустой срок здесь —
    # честное состояние, а не пробел: выдумать 24 часа значило бы выдать свою
    # догадку за требование закона.
    STAGE_SUBJECTS: "Уведомить людей, чьи данные затронуты",
}

#: Состояния срока. «Сделано» и «не наступил» — разные вещи, и путать их нельзя:
#: у первого работа закончена, у второго ещё не начиналась.
STATUS_DONE = "done"
STATUS_PENDING = "pending"
STATUS_OVERDUE = "overdue"
STATUS_NO_DEADLINE = "no_deadline"

STATUS_TITLES: dict[str, str] = {
    STATUS_DONE: "Выполнено",
    STATUS_PENDING: "Срок идёт",
    STATUS_OVERDUE: "ПРОСРОЧЕНО",
    STATUS_NO_DEADLINE: "Срок в часах законом не задан",
}


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class BreachDeadline:
    """Один срок по одной утечке."""

    stage: str
    title: str
    due_at: datetime | None
    done_at: datetime | None
    status: str
    status_title: str
    hours_left: int | None

    def as_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "title": self.title,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "done_at": self.done_at.isoformat() if self.done_at else None,
            "status": self.status,
            "status_title": self.status_title,
            "hours_left": self.hours_left,
        }


def _deadline(
    stage: str,
    *,
    discovered_at: datetime | None,
    hours: int | None,
    done_at: datetime | None,
    now: datetime,
) -> BreachDeadline:
    due_at = (
        _as_utc(discovered_at) + timedelta(hours=hours)
        if discovered_at is not None and hours is not None
        else None
    )
    if done_at is not None:
        status = STATUS_DONE
    elif due_at is None:
        status = STATUS_NO_DEADLINE
    elif due_at <= _as_utc(now):
        status = STATUS_OVERDUE
    else:
        status = STATUS_PENDING
    # Часы округляются ВНИЗ: «осталось 0 часов» честнее, чем «остался 1», когда
    # на деле осталось сорок минут.
    hours_left = (
        int((due_at - _as_utc(now)).total_seconds() // 3600)
        if due_at is not None and status == STATUS_PENDING
        else None
    )
    return BreachDeadline(
        stage=stage,
        title=STAGE_TITLES[stage],
        due_at=due_at,
        done_at=_as_utc(done_at) if done_at else None,
        status=status,
        status_title=STATUS_TITLES[status],
        hours_left=hours_left,
    )


def deadlines_for(
    *,
    discovered_at: datetime | None,
    regulator_notified_at: datetime | None,
    findings_reported_at: datetime | None,
    subjects_notified_at: datetime | None,
    now: datetime,
) -> tuple[BreachDeadline, ...]:
    """Все сроки по одной утечке.

    ``discovered_at`` — момент ОБНАРУЖЕНИЯ, его вводит человек. Пока он не
    указан, сроков нет и это видно: подставить «сейчас» значило бы сдвинуть
    отсчёт на время, прошедшее до записи.
    """

    return (
        _deadline(
            STAGE_NOTIFY,
            discovered_at=discovered_at,
            hours=NOTIFY_REGULATOR_HOURS,
            done_at=regulator_notified_at,
            now=now,
        ),
        _deadline(
            STAGE_FINDINGS,
            discovered_at=discovered_at,
            hours=REPORT_FINDINGS_HOURS,
            done_at=findings_reported_at,
            now=now,
        ),
        _deadline(
            STAGE_SUBJECTS,
            discovered_at=discovered_at,
            hours=None,
            done_at=subjects_notified_at,
            now=now,
        ),
    )
