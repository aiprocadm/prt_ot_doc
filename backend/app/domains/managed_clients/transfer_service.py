"""BIZ-49 срез-14: SQL-часть переноса данных клиента в его арендатор.

Чистые правила — в ``transfer.py``; здесь только копирование через доверенную
сессию (та же механика, что у перевода, — проверена PG-тестом фикса среза-13).

Копируются организация и сотрудники. Структурные ссылки на каталоги
аутсорсера (должность/рабочее место) обнуляются — каталоги не переносятся,
а «висячая» ссылка в чужой арендатор была бы дырой изоляции; текстовая
должность (``position_title``) сохраняется.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.managed_clients.transfer import is_person_transferable
from app.models.master_data import Company, Person

__all__ = ["TransferResult", "copy_company_with_people"]


@dataclass
class TransferResult:
    company_map: dict[str, str] = field(default_factory=dict)
    people_map: dict[str, str] = field(default_factory=dict)
    people_skipped: int = 0

    @property
    def counts(self) -> dict[str, int]:
        return {
            "company": len(self.company_map),
            "people": len(self.people_map),
            "people_skipped": self.people_skipped,
        }


_PERSON_FIELDS = (
    "first_name",
    "last_name",
    "middle_name",
    "birth_date",
    "email",
    "phone",
    "personnel_number",
    "hired_at",
    "qualifications",
    "snils",
    "passport",
    "current_ppe",
    "ppe_sizes",
    "working_conditions_class",
    "hazardous_factors",
    "position_title",
    "employment_status",
)

_COMPANY_FIELDS = (
    "name",
    "inn",
    "kpp",
    "ogrn",
    "activity_type",
    "okved_codes",
    "legal_address",
    "actual_address",
    "director",
    "phone_numbers",
)


async def copy_company_with_people(
    session: AsyncSession,
    *,
    source_tenant_id: str,
    source_company_id: str,
    target_tenant_id: str,
) -> TransferResult:
    """Скопировать организацию клиента и её сотрудников в целевой арендатор."""

    result = TransferResult()

    src_company = (
        await session.execute(
            select(Company).where(
                Company.id == source_company_id,
                Company.tenant_id == source_tenant_id,
            )
        )
    ).scalar_one()

    new_company = Company(
        tenant_id=target_tenant_id,
        **{f: getattr(src_company, f) for f in _COMPANY_FIELDS},
    )
    session.add(new_company)
    await session.flush()
    result.company_map[src_company.id] = new_company.id

    people = (
        (
            await session.execute(
                select(Person).where(
                    Person.tenant_id == source_tenant_id,
                    Person.company_id == source_company_id,
                )
            )
        )
        .scalars()
        .all()
    )
    for person in people:
        if not is_person_transferable(
            deleted_at=person.deleted_at, anonymized_at=person.anonymized_at
        ):
            result.people_skipped += 1
            continue
        copy = Person(
            tenant_id=target_tenant_id,
            company_id=new_company.id,
            # Каталожные ссылки аутсорсера в чужой арендатор не переносятся.
            position_id=None,
            workplace_id=None,
            **{f: getattr(person, f) for f in _PERSON_FIELDS},
        )
        session.add(copy)
        await session.flush()
        result.people_map[person.id] = copy.id

    return result
