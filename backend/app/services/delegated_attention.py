"""Сигналы внимания по контуру Dedicated-клиента (BIZ-49, разд. 49.1 и 49.3).

Решение о ПРАВЕ читать чужой контур принимает
``domains/managed_clients/delegation``; здесь только исполнение: открыть
сессию к арендатору клиента и посчитать те же сигналы, что считаются у
Lightweight-клиента внутри пространства аутсорсера.

## Решения

**1. Отдельная сессия к арендатору клиента, а не обход изоляции.** Сессия
привязана к контуру клиента ровно так же, как обычный запрос его собственного
пользователя: те же схема и политики строк. Никакого «системного» режима с
отключёнными правилами — он снял бы границу не только там, где нужно.

**2. Формулы просрочек НЕ переписываются.** Медосмотр, СИЗ, обучение,
удостоверения, контакты и ПБ считаются теми же условиями, что и у портфеля
(``person_scope``, ``discipline_training``, ``discipline_road_safety``,
``discipline_fire_safety``). Своя копия дала бы «просрочено» разное для
Lightweight- и Dedicated-клиента — на одном экране, в соседних строках.

**3. Организация не фильтруется.** У Dedicated-клиента ЕГО контур целиком и
есть клиент: фильтровать по организации значило бы потерять его же данные,
заведённые во второй организации.

**4. Ошибка чтения — это «не сведено», а не ноль.** Контур мог быть удалён,
переименован, недоступен. Ноль здесь читался бы как «у клиента всё в порядке»
— худшая из возможных ошибок в сводке про риски.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, or_, select

from app.db.session import AsyncSessionLocal
from app.domains.managed_clients.attention import SignalKind
from app.models.master_data import Person
from app.models.medical import MedicalExam
from app.models.ppe import PPEIssue
from app.models.road_safety import Driver
from app.models.training import TrainingEnrollment
from app.services.discipline_fire_safety import collect_fire_safety_overdue_by_company
from app.services.discipline_road_safety import expired_license_where
from app.services.discipline_training import overdue_training_enrollment_where
from app.services.person_scope import employed_person_where

__all__ = ["collect_dedicated_client_signals"]


async def collect_dedicated_client_signals(
    *, tenant_slug: str, tenant_id: str, today: date, now: datetime
) -> dict[SignalKind, int] | None:
    """Сигналы по контуру клиента; ``None`` — прочитать не удалось.

    ``None`` намеренно отличается от «нулей»: вызывающий обязан показать
    «не сведено» с причиной, а не спокойную зелёную строку.
    """

    try:
        async with AsyncSessionLocal(
            tenant=tenant_slug, tenant_id=tenant_id, create_schema=False
        ) as session:
            people = list(
                (
                    await session.execute(
                        select(Person.company_id).where(
                            Person.tenant_id == tenant_id, *employed_person_where()
                        )
                    )
                )
                .scalars()
                .all()
            )
            company_ids = [str(c) for c in people if c]

            medical = int(
                await session.scalar(
                    select(func.count())
                    .select_from(MedicalExam)
                    .join(Person, Person.id == MedicalExam.person_id)
                    .where(
                        MedicalExam.tenant_id == tenant_id,
                        MedicalExam.deleted_at.is_(None),
                        MedicalExam.valid_until < today,
                        *employed_person_where(),
                    )
                )
                or 0
            )
            ppe = int(
                await session.scalar(
                    select(func.count())
                    .select_from(PPEIssue)
                    .join(Person, Person.id == PPEIssue.person_id)
                    .where(
                        PPEIssue.tenant_id == tenant_id,
                        PPEIssue.deleted_at.is_(None),
                        # Возвращённый СИЗ не просрочен — он уже не у человека.
                        PPEIssue.returned_at.is_(None),
                        PPEIssue.expires_at.is_not(None),
                        PPEIssue.expires_at < now,
                        *employed_person_where(),
                    )
                )
                or 0
            )
            training = int(
                await session.scalar(
                    select(func.count())
                    .select_from(TrainingEnrollment)
                    .join(Person, Person.id == TrainingEnrollment.person_id)
                    .where(
                        *overdue_training_enrollment_where(tenant_id, now),
                        *employed_person_where(),
                    )
                )
                or 0
            )
            contacts = int(
                await session.scalar(
                    select(func.count())
                    .select_from(Person)
                    .where(
                        Person.tenant_id == tenant_id,
                        *employed_person_where(),
                        or_(Person.email.is_(None), Person.phone.is_(None)),
                    )
                )
                or 0
            )
            licenses = int(
                await session.scalar(
                    select(func.count())
                    .select_from(Driver)
                    .join(Person, Person.id == Driver.person_id)
                    .where(
                        *expired_license_where(tenant_id, today),
                        *employed_person_where(),
                    )
                )
                or 0
            )
            fire = 0
            if company_ids:
                by_company = await collect_fire_safety_overdue_by_company(
                    session,
                    tenant_id=tenant_id,
                    company_ids=sorted(set(company_ids)),
                    today=today,
                    now=now,
                )
                fire = sum(int(v or 0) for v in by_company.values())
    except Exception:  # pragma: no cover - контур недоступен/переименован
        return None

    return {
        SignalKind.MEDICAL_OVERDUE: medical,
        SignalKind.PPE_OVERDUE: ppe,
        SignalKind.TRAINING_OVERDUE: training,
        SignalKind.CONTACTS_MISSING: contacts,
        SignalKind.FIRE_SAFETY_OVERDUE: fire,
        SignalKind.DRIVER_LICENSE_EXPIRED: licenses,
    }
