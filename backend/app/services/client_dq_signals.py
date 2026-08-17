"""BIZ-51 срез-3 (Доп. №1 разд. 51.2): запись находок Data Quality в ленту.

Правила превращения просрочки в сигнал живут в
``app.domains.managed_clients.dq_signals`` и базы не знают. Здесь — всё
остальное: запустить проверки просрочки, понять, чей это клиент, отсеять уже
записанное и записать новое. Слой ``services`` — по той же причине, что у
импорта (ARCH-3): проверки живут в ``app.modules.data_quality``, правила — в
``app.domains``, и напрямую эти контексты друг друга не видят.

**Проверки просрочки переиспользуются, а не переписываются.** Что считается
«просрочено» — знание правил Data Quality (``ExpiredRecordsRule`` и соседи);
второй набор таких же SQL-запросов здесь разъехался бы с отчётом качества
данных при первой же правке (довод среза-5 BIZ-49 про дубль SQL). Запускаются
только три правила просрочки, а не весь движок: остальные восемь ищут дефекты
ведения учёта, которым в ленте не место (решение 1 в правилах).

**Итог честный, по слагаемым.** «Записано 3» без остального читалось бы как
«просрочки три», хотя их тридцать: остальные уже в ленте, не про клиентов или
не разобрались. Каждая причина — отдельным числом, молчаливых потерь нет.

**Потолок — только на НОВОЕ.** Ограничивать общий разбор нельзя: арендатор с
тремя сотнями давно записанных просрочек никогда не дошёл бы до свежих.

**Граница среза — та же, что у импорта: только модель Shared.** Клиент-«лайт»
живёт компанией внутри арендатора аутсорсера, его данные и лента — в одной
базе. У Dedicated данные в СВОЁМ арендаторе, проверка качества там их и видит,
а лента осталась у аутсорсера. Мост между арендаторами — отдельная работа.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.managed_clients.dq_signals import (
    EXPIRY_ENTITY_TITLES,
    ExpiryFact,
    signals_for_expiries,
)
from app.models.client_changes import ClientChange
from app.models.managed_clients import ManagedClient
from app.models.master_data import Person
from app.modules.data_quality.rules import (
    ExpiredPermitsRule,
    ExpiredPPEIssuesRule,
    ExpiredRecordsRule,
)
from app.modules.data_quality.schemas import DataQualityIssue
from app.services.client_change_signals import person_title

__all__ = ["MAX_NEW_PER_RUN", "SIGNAL_SOURCE", "DqSignalsOutcome", "collect_dq_signals"]

#: Пометка источника в ленте (влезает в String(16)).
SIGNAL_SOURCE = "data_quality"

#: Потолок НОВЫХ записей за один сбор — тот же довод, что у партии импорта:
#: лента, куда разом упало десять тысяч строк, физически не читается.
MAX_NEW_PER_RUN = 200

#: Правила Data Quality, чьи находки — «наступил срок» из таблицы разд. 51.1.
_EXPIRY_RULES = (ExpiredRecordsRule, ExpiredPermitsRule, ExpiredPPEIssuesRule)


@dataclass(frozen=True)
class DqSignalsOutcome:
    """Честный итог сбора: каждая судьба находки — отдельным числом.

    Слагаемые сходятся: ``found = recorded + already_in_feed +
    not_client_related + unparsed + deferred`` — итог, в котором числа не
    бьются, читался бы как «где-то потеряли» (урок «честного итога импорта»).
    """

    found: int
    recorded: int
    already_in_feed: int
    not_client_related: int
    unparsed: int
    #: Новые находки сверх потолка: запишутся следующим сбором.
    deferred: int
    truncated: bool


def _expired_on(issue: DataQualityIssue) -> date | None:
    """Дата истечения из находки; без неё факт не разобрать."""

    raw: Any = issue.additional_info.get("valid_until") or issue.additional_info.get(
        "expires_at"
    )
    if isinstance(raw, date):
        return raw
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _subject(issue: DataQualityIssue) -> str:
    for key in ("item_name", "permit_type"):
        value = str(issue.additional_info.get(key) or "").strip()
        if value:
            return value
    return ""


async def _person_map(
    session: AsyncSession, tenant_id: str, person_ids: set[str]
) -> dict[str, Person]:
    if not person_ids:
        return {}
    rows = (
        (
            await session.execute(
                select(Person).where(
                    Person.tenant_id == tenant_id, Person.id.in_(list(person_ids))
                )
            )
        )
        .scalars()
        .all()
    )
    return {str(person.id): person for person in rows}


async def _clients_by_company(session: AsyncSession, tenant_id: str) -> dict[str, str]:
    """company_id → managed_client_id по всем обслуживаемым клиентам.

    Собственная организация аутсорсера клиентом не является — её просрочки
    остаются в отчёте качества данных, ленту сопровождения ими не засоряем.
    """

    rows = (
        await session.execute(
            select(ManagedClient.company_id, ManagedClient.id).where(
                ManagedClient.tenant_id == tenant_id,
                ManagedClient.company_id.is_not(None),
                ManagedClient.deleted_at.is_(None),
            )
        )
    ).all()
    return {str(company_id): str(mcid) for company_id, mcid in rows if company_id}


async def _existing_refs(
    session: AsyncSession, tenant_id: str, refs: list[str]
) -> set[str]:
    if not refs:
        return set()
    rows = (
        await session.execute(
            select(ClientChange.source_ref).where(
                ClientChange.tenant_id == tenant_id,
                ClientChange.source == SIGNAL_SOURCE,
                ClientChange.source_ref.in_(refs),
            )
        )
    ).all()
    return {ref for (ref,) in rows if ref}


async def collect_dq_signals(session: AsyncSession, tenant_id: str) -> DqSignalsOutcome:
    """Разобрать просрочки Data Quality в ленты обслуживаемых клиентов.

    Ничего не коммитит — транзакцией владеет вызывающий. Повторный вызов
    записей не удваивает: личность находки включает запись и дату истечения,
    уже записанное отсеивается по ``source_ref``.
    """

    clients = await _clients_by_company(session, tenant_id)

    issues: list[DataQualityIssue] = []
    for rule_cls in _EXPIRY_RULES:
        rule = rule_cls(tenant_id, session)
        # Правило глотает свои ошибки само (пишет в лог и оставляет issues
        # пустым) — сбор продолжается по остальным, как в отчёте качества.
        await rule.check()
        issues.extend(rule.issues)

    person_ids = {
        str(issue.additional_info.get("person_id") or "")
        for issue in issues
        if issue.additional_info.get("person_id")
    }
    people = await _person_map(session, tenant_id, person_ids)

    facts: list[ExpiryFact] = []
    unparsed = 0
    not_client_related = 0
    for issue in issues:
        if issue.affected_entity_type not in EXPIRY_ENTITY_TITLES:
            unparsed += 1
            continue
        expired_on = _expired_on(issue)
        person = people.get(str(issue.additional_info.get("person_id") or ""))
        if expired_on is None or person is None:
            unparsed += 1
            continue
        company_id = str(person.company_id) if person.company_id else None
        if not company_id or company_id not in clients:
            not_client_related += 1
            continue
        facts.append(
            ExpiryFact(
                entity_type=issue.affected_entity_type,
                entity_id=str(issue.affected_entity_id),
                company_id=company_id,
                person_title=person_title(person),
                expired_on=expired_on,
                subject=_subject(issue),
            )
        )

    signals = signals_for_expiries(facts)
    refs = [signal.source_ref for signal in signals if signal.source_ref]
    existing = await _existing_refs(session, tenant_id, refs)

    fresh = [signal for signal in signals if signal.source_ref not in existing]
    truncated = len(fresh) > MAX_NEW_PER_RUN
    to_record = fresh[:MAX_NEW_PER_RUN]

    for signal in to_record:
        session.add(
            ClientChange(
                tenant_id=tenant_id,
                managed_client_id=clients[signal.company_id],
                kind=signal.kind,
                happened_on=signal.happened_on,
                summary=signal.summary,
                details=signal.details,
                source=SIGNAL_SOURCE,
                source_ref=signal.source_ref,
            )
        )
    if to_record:
        await session.flush()

    return DqSignalsOutcome(
        found=len(issues),
        recorded=len(to_record),
        already_in_feed=len(existing),
        not_client_related=not_client_related,
        unparsed=unparsed,
        deferred=len(fresh) - len(to_record),
        truncated=truncated,
    )
