"""BIZ-51 срез-2 (Доп. №1 разд. 51.2): запись сигналов импорта в ленту клиента.

Правила diff'а живут в ``app.domains.managed_clients.import_signals`` и базы не
знают. Здесь — всё остальное: сходить за фактами, понять, чей это клиент, и
записать. Слой ``services`` выбран не для красоты: ARCH-3 запрещает
``app.modules.*`` импортировать ``app.domains.*``, а вызывать это должен именно
модуль импорта. ``modules → services`` разрешено, поэтому посредник тут.

**Сигнал не может провалить импорт.** Данные уже записаны и закоммичены; если
разбор упал, правильный исход — «лента не пополнилась», а не откат чужой
успешной загрузки и 500 в ответ. Тот же довод, что у проверок качества
(``modules/imports/quality.py``).

**Разбор партии одноразовый.** Ретрай брокера или повторный вызов ручки не
должны удваивать ленту: дубликаты в ней хуже пропусков — специалист дважды
сделает одну работу или перестанет верить списку. Признак «уже разбирали» —
наличие записей с ``source_ref`` этой партии.

**Граница среза: только модель Shared.** Клиент-«лайт» живёт компанией внутри
арендатора аутсорсера — импорт и лента там в одной базе, и связь находится по
``ManagedClient.company_id``. У клиента, переведённого в Dedicated, данные
переехали в СВОЙ арендатор: загрузка идёт туда, а ``ManagedClient`` и лента
остались у аутсорсера, поэтому сигналы до неё не дойдут. Мост между
арендаторами — отдельная работа, а не хвост этого среза; молча делать вид, что
он есть, хуже, чем назвать границу.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.managed_clients.import_signals import (
    SIGNAL_TARGETS,
    ChangeSignal,
    RowFact,
    signals_for_batch,
)
from app.models.client_changes import ClientChange
from app.models.imports import ImportBatch, ImportRow
from app.models.managed_clients import ManagedClient
from app.models.master_data import Person, Position, Site
from app.services.events import EventType
from app.services.outbox import OutboxService

__all__ = [
    "SIGNAL_SOURCE",
    "enqueue_change_recorded",
    "person_title",
    "record_client_changes_for_batch",
]

logger = logging.getLogger(__name__)

#: Пометка источника в ленте.
SIGNAL_SOURCE = "import"

#: Какая модель стоит за целью импорта.
_MODELS: dict[str, Any] = {
    "persons": Person,
    "positions": Position,
    "sites": Site,
}

#: Планировщик импорта говорит «create/update», а в ``import_row`` ложится
#: прошедшее время — «created/updated». Два словаря в одном модуле уже стоили
#: этому срезу молчаливо пустой ленты: фильтр по «create» не совпадал ни с чем,
#: и импорт исправно не порождал НИЧЕГО. Перевод держим здесь, одной таблицей,
#: чтобы правила не зависели от чужих слов, а рассинхрон ловил тест.
ROW_ACTIONS: dict[str, str] = {"created": "create", "updated": "update"}


def person_title(entity: Person) -> str:
    parts = [entity.last_name or "", entity.first_name or "", entity.middle_name or ""]
    return " ".join(part for part in parts if part).strip()


async def enqueue_change_recorded(
    session: AsyncSession, rows: Sequence[ClientChange]
) -> None:
    """BIZ-51 срез-9: каждая новая запись ленты — событие в outbox.

    Через событие запись видят rules engine (правила «если у клиента X, то
    создать задачу Y» — четвёртый источник разд. 51.2 в готовом конструкторе)
    и вебхуки подписчиков. Зовётся ДО commit: строка ленты и событие о ней —
    одна транзакция, иначе сбой между ними дал бы запись без правила или
    правило без записи.
    """

    if not rows:
        return
    svc = OutboxService(session)
    for row in rows:
        await svc.enqueue(
            tenant_id=str(row.tenant_id),
            event_type=EventType.CLIENT_CHANGE_RECORDED.value,
            payload={
                "tenant_id": str(row.tenant_id),
                "change_id": str(row.id),
                "managed_client_id": str(row.managed_client_id),
                "kind": getattr(row.kind, "value", str(row.kind)),
                "summary": row.summary,
                "happened_on": row.happened_on.isoformat(),
                "source": row.source or "manual",
            },
        )


def _now_values(target: str, entity: Any) -> dict[str, Any]:
    """Текущее состояние полей, на которые смотрят правила."""

    if target != "persons":
        return {}
    status = getattr(entity, "employment_status", None)
    return {
        "employment_status": getattr(status, "value", status),
        "position_id": entity.position_id,
        "position_title": entity.position_title,
        "hired_at": entity.hired_at,
    }


async def _initial_load_companies(
    session: AsyncSession, target: str, batch: ImportBatch, companies: set[str]
) -> set[str]:
    """Компании, у которых до этой партии не было ни одной такой записи.

    Именно это отличает «привезли штатку впервые» от «приняли людей»: без
    прошлого состояния сравнивать не с чем, и объявлять пятьсот переносов
    пятьюстами приёмами на работу — вранье, которое лента не переживёт.
    """

    if not companies:
        return set()
    model = _MODELS[target]
    cutoff = batch.applied_at or datetime.now(timezone.utc)
    stmt: Select[Any] = (
        select(model.company_id)
        .where(
            model.tenant_id == batch.tenant_id,
            model.company_id.in_(companies),
            model.created_at < cutoff,
        )
        .group_by(model.company_id)
    )
    had_before = {row[0] for row in (await session.execute(stmt)).all()}
    return {cid for cid in companies if cid not in had_before}


async def _collect_facts(
    session: AsyncSession, target: str, batch: ImportBatch
) -> tuple[list[RowFact], set[str]]:
    rows = (
        await session.execute(
            select(ImportRow).where(
                ImportRow.tenant_id == batch.tenant_id,
                ImportRow.batch_id == batch.id,
                ImportRow.action.in_(tuple(ROW_ACTIONS)),
                ImportRow.entity_id.is_not(None),
            )
        )
    ).scalars()
    by_entity = {str(row.entity_id): row for row in rows if row.entity_id}
    if not by_entity:
        return [], set()

    model = _MODELS[target]
    entities = (
        (
            await session.execute(
                select(model).where(
                    model.tenant_id == batch.tenant_id, model.id.in_(list(by_entity))
                )
            )
        )
        .scalars()
        .all()
    )

    facts: list[RowFact] = []
    companies: set[str] = set()
    for entity in entities:
        row = by_entity.get(str(entity.id))
        if row is None or not entity.company_id:
            continue
        companies.add(str(entity.company_id))
        title = person_title(entity) if target == "persons" else (entity.name or "")
        facts.append(
            RowFact(
                target=target,
                action=ROW_ACTIONS.get(str(row.action), str(row.action)),
                company_id=str(entity.company_id),
                title=title,
                entity_id=str(entity.id),
                before=dict(row.before_values or {}),
                now=_now_values(target, entity),
            )
        )
    return facts, companies


async def _clients_by_company(
    session: AsyncSession, tenant_id: str, companies: set[str]
) -> dict[str, str]:
    """company_id → managed_client_id.

    Компания, которая не обслуживается как клиент (например, собственная
    организация аутсорсера), сигналов не даёт: ленту сопровождения ведут по
    клиенту, и вешать в неё свои же кадровые события незачем.
    """

    if not companies:
        return {}
    rows = (
        await session.execute(
            select(ManagedClient.company_id, ManagedClient.id).where(
                ManagedClient.tenant_id == tenant_id,
                ManagedClient.company_id.in_(companies),
                ManagedClient.deleted_at.is_(None),
            )
        )
    ).all()
    return {str(company_id): str(mcid) for company_id, mcid in rows if company_id}


async def _already_recorded(session: AsyncSession, batch: ImportBatch) -> bool:
    found = (
        await session.execute(
            select(ClientChange.id)
            .where(
                ClientChange.tenant_id == batch.tenant_id,
                ClientChange.source_ref == batch.id,
            )
            .limit(1)
        )
    ).first()
    return found is not None


def _applied_on(batch: ImportBatch) -> date:
    moment = batch.finished_at or batch.applied_at
    return moment.date() if moment else datetime.now(timezone.utc).date()


async def record_client_changes_for_batch(
    session: AsyncSession, batch: ImportBatch
) -> Sequence[ChangeSignal]:
    """Разобрать применённую партию в ленты обслуживаемых клиентов.

    Возвращает записанные сигналы (пустой список — законный исход: партия
    могла не касаться клиентов или быть первичной загрузкой). Исключения
    наружу не выпускаются.
    """

    if batch.mode == "preview" or batch.status != "applied":
        return ()
    if batch.target not in SIGNAL_TARGETS:
        return ()

    try:
        if await _already_recorded(session, batch):
            return ()

        facts, companies = await _collect_facts(session, batch.target, batch)
        if not facts:
            return ()

        clients = await _clients_by_company(session, str(batch.tenant_id), companies)
        if not clients:
            return ()

        initial = await _initial_load_companies(session, batch.target, batch, set(clients))
        signals = signals_for_batch(
            batch.target,
            [fact for fact in facts if fact.company_id in clients],
            applied_on=_applied_on(batch),
            initial_load_companies=initial,
        )
        created_rows: list[ClientChange] = []
        for signal in signals:
            row = ClientChange(
                tenant_id=batch.tenant_id,
                managed_client_id=clients[signal.company_id],
                kind=signal.kind,
                happened_on=signal.happened_on,
                summary=signal.summary,
                details=signal.details,
                source=SIGNAL_SOURCE,
                source_ref=batch.id,
            )
            session.add(row)
            created_rows.append(row)
        await session.flush()
        # Срез-9: записи ленты — события (в той же транзакции и в том же
        # try: событие не должно провалить импорт, как и сам сигнал).
        await enqueue_change_recorded(session, created_rows)
    except Exception:  # noqa: BLE001 — разбор трогает половину master-data
        logger.exception("imports.client_changes_failed", extra={"batch_id": batch.id})
        return ()

    return signals
