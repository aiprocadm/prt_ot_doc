"""Просроченные сроки дисциплин → события для правил (BIZ-54-57 срез-62).

Доп. №1 разд. 57.3 и приёмка §58.3: «для каждой дисциплины есть библиотека
предустановленных правил». Правило живёт от события, а экология, ГО и ЧС и
БДД событий не испускали вовсе — три клетки библиотеки стояли пустыми
«с причиной». Причина была честной, но клетки от этого не заполнялись.

## Откуда берётся событие

Не из модулей — из ОБЩЕГО календаря. Каждый из трёх контуров уже размечен
источниками сроков (разрешения и замеры ПЭК, ЭПБ устройств, учения ГО,
документы ТС, водительские удостоверения), и Центр внимания с разрезом
руководителя считают просрочки по ним одной формулой
(``discipline_attention``). Ежедневный обход берёт ТЕ ЖЕ строки с ТЕМ ЖЕ
``is_overdue`` и превращает каждую просрочку в событие
``DisciplineDeadlineOverdue``. Второй расчёт «что просрочено» рядом
с первым разошёлся бы с ним на первой же правке — тогда правило сработало
бы там, где Центр внимания молчит, или наоборот.

## Решения

* **Событие — одно на (запись, срок).** Ключ включает сам просроченный срок,
  а не день обхода: просрочка наступает один раз, и задача по ней нужна одна.
  Продлили и снова просрочили — новый срок, новое событие. (У СИЗ ключ с днём
  — там намеренно ежедневное напоминание, здесь оно плодило бы задачи.)
* **Ядро — только по названной причине.** У медосмотров и СИЗ события
  просрочки свои, второе дало бы две задачи. У сроков обучения — удостоверения
  (срез-76) и назначения (срез-78) — событий нет, поэтому они в обходе;
  список ``CORE_DEADLINE_SOURCES`` закрытый.
* **Только применимые дисциплины.** Библиотека выдаётся всем арендаторам,
  движок правил проверяет лишь свой модуль. Без этой границы арендатор без
  «Экологии», но с внесёнными разрешениями получал бы задачи эколога — то
  самое «есть и выключено», которого BIZ-53 велит не путать с «выдано».
  Факты в сводках остаются (срез-56), автоматика выключенного модуля молчит.
* **Окно — как у Центра внимания** (``DISCIPLINE_LOOKBACK``): просрочка
  полугодовой давности — разбор архива, а не событие. Обход первого дня не
  завалит арендатора задачами по всему, что когда-либо истекло.
* **Потолок честный.** Календарь отдаёт первые 50 строк на источник — для
  экрана. Обходу нужна каждая просроченная строка, поэтому потолок поднят
  (``DEADLINE_EVENTS_LIMIT``); если источник упёрся и в него, это названо
  в итоге (``truncated``), а не проглочено молча.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.disciplines import SOURCE_DISCIPLINE, Discipline
from app.models.models import Outbox
from app.services.calendar_aggregator import CalendarAggregatorService
from app.services.discipline_applicability import collect_applicability
from app.services.discipline_attention import DISCIPLINE_LOOKBACK
from app.services.events import EventType, discipline_deadline_key
from app.services.outbox import OutboxService

__all__ = [
    "CORE_DEADLINE_SOURCES",
    "DEADLINE_DISCIPLINES",
    "DEADLINE_EVENTS_LIMIT",
    "DEADLINE_EVENT_SOURCES",
    "DeadlineEventsOutcome",
    "emit_overdue_deadline_events",
]

#: Источники ядра, которым обход всё же нужен (срез-76). Правило «ядро не
#: входит» держится на том, что у ядра свои события просрочки. У срока
#: удостоверения по обучению (``TrainingCertificate.valid_until``) события
#: нет вовсе: ``TrainingCompleted`` и ``TrainingAssigned`` — про другое, а
#: снимок ``compliance_deadline`` обновляется только кнопкой и событий не
#: даёт. Второй задачи на ту же просрочку взяться неоткуда. Срок назначения
#: на обучение (``TrainingEnrollment.due_at``, срез-77/78) — та же история:
#: ``TrainingAssigned`` рождается в момент назначения, об истечении срока
#: никто не сообщает. Список закрытый: новый источник ядра сюда попадает
#: только с названной причиной.
CORE_DEADLINE_SOURCES: frozenset[str] = frozenset({"training_certificate", "training_enrollment"})

#: Источники календаря, чьи просрочки становятся событиями. Это сроки пяти
#: дисциплин Доп. №1: у их контуров нет своих событий просрочки. Ядро
#: (медосмотры, СИЗ, обучение, наряды) сюда НЕ входит — у него события свои
#: (``TaskOverdue`` медосмотров, ``PPEReplacementDue``), и второе событие
#: на ту же просрочку дало бы две задачи. Исключения ядра — только из
#: ``CORE_DEADLINE_SOURCES`` (стережёт ``tests/test_discipline_deadline_events``).
DEADLINE_EVENT_SOURCES: tuple[str, ...] = (
    "ecology_permit",
    "ecology_measurement",
    # срез-72: срок 2-ТП / декларации / платежа, внесённый экологом (срез-71).
    # Исполненный срок календарь не отдаёт, поэтому событие получает только
    # несданное; вид (report / payment) уходит в ключ и payload.
    "ecology_report",
    "industrial_safety_epb",
    "civil_defense_drill",
    "road_safety_vehicle",
    "road_safety_driver",
    # срез-76: истёкшее удостоверение по обучению (источник срез-75). Ядро,
    # но своего события у срока нет — см. CORE_DEADLINE_SOURCES. Обучение
    # применимо всегда (модуля нет), поэтому обход больше не бывает пустым.
    "training_certificate",
    # срез-78: просроченное назначение на обучение (источник срез-77). Ядро,
    # событий об истечении срока нет — см. CORE_DEADLINE_SOURCES.
    "training_enrollment",
    # срез-79: перезарядка и поверка средств ПБ (источник срез-79). Модуль
    # ПБ считает просрочку только при чтении сводки, событий не шлёт. Вид
    # (recharge / inspection) уходит в ключ: у огнетушителя оба срока.
    "fire_safety_equipment",
)

#: Дисциплины, у которых обход вообще есть — для честного «пропущено».
DEADLINE_DISCIPLINES: frozenset[Discipline] = frozenset(
    SOURCE_DISCIPLINE[source] for source in DEADLINE_EVENT_SOURCES
)

#: Потолок строк на источник за один обход.
DEADLINE_EVENTS_LIMIT = 500


@dataclass(frozen=True)
class DeadlineEventsOutcome:
    """Что сделал обход — числа для журнала тика, не для экрана."""

    emitted: int = 0
    #: Дисциплины, пропущенные как неприменимые (модуль не выдан/выключен).
    skipped: tuple[Discipline, ...] = ()
    #: Источники, упёршиеся в потолок: часть просрочек не обойдена.
    truncated: tuple[str, ...] = field(default_factory=tuple)


async def _outbox_key_exists(session: AsyncSession, *, tenant_id: str, key: str) -> bool:
    """Ключ уже в outbox — под любым назначением (см. ``ppe_notifications``)."""

    stmt = (
        select(Outbox.id)
        .where(Outbox.tenant_id == tenant_id, Outbox.idempotency_key == key)
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def emit_overdue_deadline_events(
    session: AsyncSession,
    *,
    tenant_id: str,
    now: datetime | None = None,
) -> DeadlineEventsOutcome:
    """Обойти просроченные сроки применимых дисциплин и завести события.

    Ничего не коммитит — транзакцией владеет вызывающий. Возвращает число
    ДЕЙСТВИТЕЛЬНО новых событий: повтор обхода в тот же день даёт ноль.
    """

    now = now or datetime.now(tz=timezone.utc)
    applicability = await collect_applicability(session, tenant_id)
    sources = tuple(
        source
        for source in DEADLINE_EVENT_SOURCES
        if applicability.applies(SOURCE_DISCIPLINE[source])
    )
    skipped = tuple(d for d in applicability.hidden if d in DEADLINE_DISCIPLINES)
    if not sources:
        return DeadlineEventsOutcome(skipped=skipped)

    service = CalendarAggregatorService(
        tenant_id=tenant_id, db=session, limit=DEADLINE_EVENTS_LIMIT
    )
    response = await service.list_events(
        from_at=now - DISCIPLINE_LOOKBACK,
        to_at=now,
        source_types=sources,
        include_sla=True,
    )

    outbox = OutboxService(session)
    emitted = 0
    for item in response.items:
        if not item.is_overdue:
            continue
        discipline = SOURCE_DISCIPLINE[item.source_type]
        kind = item.extra.get("kind")
        due_on = item.starts_at.date()
        key = discipline_deadline_key(
            source_type=item.source_type,
            source_id=item.source_id,
            kind=str(kind) if kind else None,
            due_on=due_on,
        )
        if await _outbox_key_exists(session, tenant_id=tenant_id, key=key):
            continue
        await outbox.enqueue(
            tenant_id=tenant_id,
            event_type=EventType.DISCIPLINE_DEADLINE_OVERDUE.value,
            idempotency_key=key,
            payload={
                "tenant_id": tenant_id,
                "discipline": discipline.value,
                "source_type": item.source_type,
                "source_id": item.source_id,
                "title": item.title,
                "due_at": item.starts_at.isoformat(),
                "days_overdue": max((now.date() - due_on).days, 0),
                "kind": str(kind) if kind else None,
                "person_id": item.person_id,
                "site_id": item.site_id,
                "company_id": item.company_id,
            },
        )
        emitted += 1

    truncated = tuple(
        row.source_type for row in response.by_source if row.count > DEADLINE_EVENTS_LIMIT
    )
    return DeadlineEventsOutcome(emitted=emitted, skipped=skipped, truncated=truncated)
