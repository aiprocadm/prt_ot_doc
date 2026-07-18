"""Гонка дублей briefing-подписей: unique-индекс + честный 409 вместо 500.

Сценарий гонки: два конкурентных подписания одного briefing_entry одним
signer_type оба проходят existing-check (окно гонки) и оба INSERT'ят.
Unique-индекс uq_briefing_signatures_entry_signer ловит второй INSERT;
писатель обязан превратить IntegrityError в конфликт, а не в 500.

Окно гонки моделируется monkeypatch'ем existing-check'а (_find_existing → None).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.models import BriefingEntry, BriefingJournal, BriefingSignature, RoleEnum
from app.modules.briefings.services import BriefingEntryService, BriefingSignatureConflict


def test_orm_declares_unique_index_matching_migration():
    """ORM↔migration parity: индекс объявлен в __table_args__ модели."""
    table = BriefingSignature.__table__
    matches = [idx for idx in table.indexes if idx.name == "uq_briefing_signatures_entry_signer"]
    assert len(matches) == 1
    idx = matches[0]
    assert idx.unique is True
    assert [col.name for col in idx.columns] == ["briefing_entry_id", "signer_type"]


async def _entry(session, data_factory, *, code: str):
    tenant = await data_factory.ensure_tenant(session=session)
    company = await data_factory.create_company(
        tenant=tenant, session=session, name=f"BRF UQ {code}"
    )
    person = await data_factory.create_person(tenant=tenant, company=company, session=session)
    journal = BriefingJournal(
        tenant_id=tenant.id,
        code=f"BRF-UQ-{code}",
        title="Unique Race Journal",
        journal_type="workplace",
        status="active",
    )
    session.add(journal)
    await session.flush()
    entry = BriefingEntry(
        tenant_id=tenant.id,
        person_id=person.id,
        briefing_journal_id=journal.id,
        briefing_type="primary",
        briefing_date=datetime.now(tz=timezone.utc),
        status="assigned",
    )
    session.add(entry)
    await session.flush()
    return tenant, entry


@pytest.mark.asyncio
async def test_service_race_duplicate_raises_conflict_not_second_row(
    sessionmaker, data_factory, monkeypatch
):
    async with sessionmaker() as session:
        tenant, entry = await _entry(session, data_factory, code="S1")
        entry_id = entry.id
        await BriefingEntryService().sign(session, entry, "employee", None)
        await session.commit()

    # Окно гонки: existing-check «не видит» конкурентную вставку.
    async def _race_window(self, session, entry_id, signer_type):
        return None

    monkeypatch.setattr(BriefingEntryService, "_find_existing", _race_window)

    async with sessionmaker() as session:
        entry = await session.get(BriefingEntry, entry_id)
        with pytest.raises(BriefingSignatureConflict):
            await BriefingEntryService().sign(session, entry, "employee", None)

    async with sessionmaker() as session:
        rows = (
            (
                await session.execute(
                    select(BriefingSignature).where(
                        BriefingSignature.briefing_entry_id == entry_id,
                        BriefingSignature.signer_type == "employee",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1, "гонка не должна оставить второй ряд"


@pytest.mark.asyncio
async def test_api_race_duplicate_returns_409_not_500(
    async_client, sessionmaker, data_factory, make_auth_headers, monkeypatch
):
    async with sessionmaker() as session:
        tenant, entry = await _entry(session, data_factory, code="A1")
        entry_id = entry.id
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    first = await async_client.post(
        f"/api/v1/briefings/entries/{entry_id}/sign-employee",
        json={"signer_user_id": "user-1"},
        headers=headers,
    )
    assert first.status_code == 200, first.text

    # Окно гонки: existing-check отключён — второй запрос идёт прямо в INSERT.
    async def _race_window(self, session, entry_id, signer_type):
        return None

    monkeypatch.setattr(BriefingEntryService, "_find_existing", _race_window)

    second = await async_client.post(
        f"/api/v1/briefings/entries/{entry_id}/sign-employee",
        json={"signer_user_id": "user-2"},
        headers=headers,
    )
    assert second.status_code == 409, second.text
    assert second.json()["detail"]["code"] == "BRIEFING_SIGNATURE_CONFLICT"

    async with sessionmaker() as session:
        rows = (
            (
                await session.execute(
                    select(BriefingSignature).where(
                        BriefingSignature.briefing_entry_id == entry_id,
                        BriefingSignature.signer_type == "employee",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_repeat_sign_without_race_stays_idempotent(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    """Контракт Среза-1 не сломан: без гонки повторная подпись идемпотентна (200)."""
    async with sessionmaker() as session:
        tenant, entry = await _entry(session, data_factory, code="I1")
        entry_id = entry.id
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    first = await async_client.post(
        f"/api/v1/briefings/entries/{entry_id}/sign-employee",
        json={"signer_user_id": "user-1"},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    second = await async_client.post(
        f"/api/v1/briefings/entries/{entry_id}/sign-employee",
        json={"signer_user_id": "user-1"},
        headers=headers,
    )
    assert second.status_code == 200, second.text
    assert second.json()["signature"]["id"] == first.json()["signature"]["id"]
