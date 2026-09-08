"""BIZ-49 срез-2: сбор сигналов внимания по портфелю клиентов (разд. 49.2).

Отделено от чистых правил (``attention.py``): здесь только SQL и склейка,
все решения «что важнее» живут в правилах.

**Почему считаем по организации клиента.** У режима Lightweight клиент — это
организация внутри пространства аутсорсера, поэтому сотрудники клиента
находятся через ``Person.company_id``, а их просрочки — через ``person_id``.
У режима Dedicated данные лежат в ДРУГОМ арендаторе: до делегированного
доступа (разд. 49.3) читать их нечем, и такие клиенты помечаются
``not_aggregated`` вместо тихого нуля.

**Один запрос на сигнал, а не на клиента.** Портфель бывает на сотню клиентов;
запрос в цикле дал бы сотни round-trip'ов на каждое открытие экрана. Просрочки
ПБ (срез-87) поэтому считает ``collect_fire_safety_overdue_by_company`` — по
всем организациям разом, теми же слагаемыми, что светофор клиента; истёкшие
удостоверения водителей (срез-88) — одним сгруппированным запросом по правилу
``discipline_road_safety.expired_license_where``.

**Уволенный не в счёт (срез-89).** Все поимённые сигналы берут людей одним
правилом ``person_scope.employed_person_where`` — тем же, что светофор
клиента, площадка 360° и карточка сотрудника: истёкший медосмотр уволенного
— история, а не разрыв, и портфель не должен гореть там, где светофор того
же клиента чист.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.managed_clients.attention import (
    ClientAttention,
    SignalKind,
    build_client_attention,
    not_aggregated,
    sort_portfolio,
)
from app.domains.managed_clients.consent import ClientConsent
from app.domains.managed_clients.delegation import evaluate_delegated_read
from app.domains.managed_clients.lifecycle import ManagedClientMode, is_contract_expiring
from app.models.managed_clients import ManagedClient, ManagedClientConsent
from app.models.master_data import Person
from app.models.medical import MedicalExam
from app.models.ppe import PPEIssue
from app.models.road_safety import Driver
from app.models.tenanting import Tenant
from app.models.training import TrainingEnrollment
from app.services.delegated_attention import collect_dedicated_client_signals
from app.services.discipline_fire_safety import collect_fire_safety_overdue_by_company
from app.services.discipline_road_safety import expired_license_where
from app.services.discipline_training import overdue_training_enrollment_where
from app.services.person_scope import employed_person_where

__all__ = ["DEDICATED_REASON", "collect_portfolio_attention"]

DEDICATED_REASON = (
    "Данные ведутся в отдельном контуре клиента; сводка станет доступна "
    "после подключения делегированного доступа"
)

#: Контур прочитать не удалось (удалён, переименован, недоступен). Ноль здесь
#: читался бы как «у клиента всё в порядке» — худшая ошибка в сводке про риски.
DELEGATED_READ_FAILED_REASON = "Контур клиента сейчас недоступен — сводка по нему не собрана"


async def _delegated_signals(
    session: AsyncSession,
    *,
    client: ManagedClient,
    outsourcer_tenant_id: str,
    today: date,
    now: datetime,
) -> tuple[dict[SignalKind, int] | None, str]:
    """Сигналы по контуру Dedicated-клиента или причина, почему их нет.

    Право читать чужой контур проверяется ЗДЕСЬ и целиком (иерархия арендаторов
    плюс действующее согласие); само чтение — в ``services/delegated_attention``.
    """

    slug = (client.dedicated_tenant_slug or "").strip()
    client_tenant = None
    if slug:
        client_tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == slug))
        ).scalar_one_or_none()

    consents = [
        ClientConsent(
            client_id=str(row.managed_client_id),
            document_ref=row.document_ref,
            granted_at=row.granted_at,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
        )
        for row in (
            (
                await session.execute(
                    select(ManagedClientConsent).where(
                        ManagedClientConsent.tenant_id == outsourcer_tenant_id,
                        ManagedClientConsent.managed_client_id == client.id,
                    )
                )
            )
            .scalars()
            .all()
        )
    ]

    verdict = evaluate_delegated_read(
        mode=client.mode,
        client_tenant_slug=slug or None,
        client_tenant_exists=client_tenant is not None,
        client_tenant_parent_id=getattr(client_tenant, "parent_id", None),
        client_tenant_is_active=bool(getattr(client_tenant, "is_active", False)),
        outsourcer_tenant_id=outsourcer_tenant_id,
        consents=consents,
        now=now,
    )
    if not verdict.allowed:
        return None, verdict.reason or DEDICATED_REASON

    counts = await collect_dedicated_client_signals(
        tenant_slug=str(verdict.tenant_slug),
        tenant_id=str(client_tenant.id),
        today=today,
        now=now,
    )
    if counts is None:
        return None, DELEGATED_READ_FAILED_REASON
    return counts, ""


async def _count_by_company(session: AsyncSession, stmt) -> dict[str, int]:
    rows = (await session.execute(stmt)).all()
    return {str(company_id): int(count or 0) for company_id, count in rows if company_id}


async def collect_portfolio_attention(
    session: AsyncSession,
    *,
    tenant_id: str,
    today: date,
    now: datetime | None = None,
    horizon_days: int,
) -> list[ClientAttention]:
    """Сводка внимания по всем ведомым клиентам арендатора."""

    now = now or datetime.now(tz=timezone.utc)

    clients = list(
        (
            await session.execute(
                select(ManagedClient).where(
                    ManagedClient.tenant_id == tenant_id,
                    ManagedClient.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not clients:
        return []

    lightweight = [c for c in clients if c.mode is ManagedClientMode.LIGHTWEIGHT and c.company_id]
    company_ids = {c.company_id for c in lightweight if c.company_id}

    medical: dict[str, int] = {}
    ppe: dict[str, int] = {}
    training: dict[str, int] = {}
    contacts: dict[str, int] = {}
    fire_safety: dict[str, int] = {}
    licenses: dict[str, int] = {}

    if company_ids:
        medical = await _count_by_company(
            session,
            select(Person.company_id, func.count())
            .select_from(MedicalExam)
            .join(Person, Person.id == MedicalExam.person_id)
            .where(
                MedicalExam.tenant_id == tenant_id,
                MedicalExam.deleted_at.is_(None),
                MedicalExam.valid_until < today,
                Person.company_id.in_(company_ids),
                *employed_person_where(),
            )
            .group_by(Person.company_id),
        )
        ppe = await _count_by_company(
            session,
            select(Person.company_id, func.count())
            .select_from(PPEIssue)
            .join(Person, Person.id == PPEIssue.person_id)
            .where(
                PPEIssue.tenant_id == tenant_id,
                PPEIssue.deleted_at.is_(None),
                # Возвращённый СИЗ не просрочен — он уже не у человека.
                PPEIssue.returned_at.is_(None),
                PPEIssue.expires_at.is_not(None),
                PPEIssue.expires_at < now,
                Person.company_id.in_(company_ids),
                *employed_person_where(),
            )
            .group_by(Person.company_id),
        )
        training = await _count_by_company(
            session,
            select(Person.company_id, func.count())
            .select_from(TrainingEnrollment)
            .join(Person, Person.id == TrainingEnrollment.person_id)
            .where(
                # Формула просрочки одна с общим календарём (срез-77).
                *overdue_training_enrollment_where(tenant_id, now),
                Person.company_id.in_(company_ids),
                *employed_person_where(),
            )
            .group_by(Person.company_id),
        )
        contacts = await _count_by_company(
            session,
            select(Person.company_id, func.count())
            .where(
                Person.tenant_id == tenant_id,
                *employed_person_where(),
                Person.company_id.in_(company_ids),
                or_(Person.email.is_(None), Person.phone.is_(None)),
            )
            .group_by(Person.company_id),
        )
        fire_safety = await collect_fire_safety_overdue_by_company(
            session, tenant_id=tenant_id, company_ids=list(company_ids), today=today, now=now
        )
        licenses = await _count_by_company(
            session,
            select(Person.company_id, func.count())
            .select_from(Driver)
            .join(Person, Person.id == Driver.person_id)
            .where(
                # Только допущенные водители — одно правило со светофором клиента
                # и календарём (срез-88).
                *expired_license_where(tenant_id, today),
                Person.company_id.in_(company_ids),
                *employed_person_where(),
            )
            .group_by(Person.company_id),
        )

    rows: list[ClientAttention] = []
    for client in clients:
        expiring = is_contract_expiring(
            client.contract_status,
            client.contract_ends_at,
            today=today,
            horizon_days=horizon_days,
        )
        if client.mode is ManagedClientMode.DEDICATED:
            # Срез-126: контур клиента читается делегированно — если для этого
            # есть основание (иерархия арендаторов) и согласие клиента.
            counts, reason = await _delegated_signals(
                session,
                client=client,
                outsourcer_tenant_id=tenant_id,
                today=today,
                now=now,
            )
            if counts is not None:
                rows.append(
                    build_client_attention(
                        client_id=client.id,
                        client_name=client.name,
                        counts=counts,
                        contract_expiring=expiring,
                    )
                )
                continue
            row = not_aggregated(client_id=client.id, client_name=client.name, reason=reason)
            if expiring:
                row = ClientAttention(
                    client_id=row.client_id,
                    client_name=row.client_name,
                    aggregation=row.aggregation,
                    signals=build_client_attention(
                        client_id=client.id,
                        client_name=client.name,
                        counts={},
                        contract_expiring=True,
                    ).signals,
                    total=None,
                    severity=None,
                    reason=row.reason,
                )
            rows.append(row)
            continue

        if not client.company_id:
            # Договор ведёт аутсорсер, и он виден всегда; остальное — не читаем.
            row = not_aggregated(
                client_id=client.id, client_name=client.name, reason=DEDICATED_REASON
            )
            if expiring:
                row = ClientAttention(
                    client_id=row.client_id,
                    client_name=row.client_name,
                    aggregation=row.aggregation,
                    signals=build_client_attention(
                        client_id=client.id,
                        client_name=client.name,
                        counts={},
                        contract_expiring=True,
                    ).signals,
                    total=None,
                    severity=None,
                    reason=row.reason,
                )
            rows.append(row)
            continue

        cid = client.company_id
        rows.append(
            build_client_attention(
                client_id=client.id,
                client_name=client.name,
                counts={
                    SignalKind.MEDICAL_OVERDUE: medical.get(cid, 0),
                    SignalKind.PPE_OVERDUE: ppe.get(cid, 0),
                    SignalKind.TRAINING_OVERDUE: training.get(cid, 0),
                    SignalKind.CONTACTS_MISSING: contacts.get(cid, 0),
                    SignalKind.FIRE_SAFETY_OVERDUE: fire_safety.get(cid, 0),
                    SignalKind.DRIVER_LICENSE_EXPIRED: licenses.get(cid, 0),
                },
                contract_expiring=expiring,
            )
        )

    return sort_portfolio(rows)
