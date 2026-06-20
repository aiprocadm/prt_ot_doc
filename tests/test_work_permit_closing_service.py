"""Ф3b сервис: record_completion, гейт close (без подписей → ошибка; с актом+сдал+принял → ок).

Персоны создаются через ``create_person()`` ДО открытия тестовой сессии (своя
транзакция с commit) — проверенный паттерн Ф2 (``tests/test_work_permit_signing.py``):
создавать персон внутри тестовой сессии нельзя (фабрика делает ``session.commit()``
посреди теста + конкурентный доступ к общему SQLite-файлу).
"""
from __future__ import annotations

import pytest

from app.domains.work_permits import lifecycle as lc
from app.domains.work_permits import service as svc
from app.domains.work_permits.signing import (
    WorkPermitSignerError, sign_closing,
)
from app.services.pep_signing import PepConflict


async def _persons(data_factory, *names):
    """tenant+company создаются ОДИН раз, по персоне на имя — общая компания снимает
    UNIQUE-конфликт company.(tenant_id, name) при нескольких членах бригады.
    Возвращает (tenant_id, [person, ...])."""
    tenant = await data_factory.ensure_tenant()
    company = await data_factory.create_company(tenant=tenant)
    people = []
    for i, nm in enumerate(names):
        people.append(await data_factory.create_person(
            tenant=tenant, company=company, first_name=nm, last_name=f"P{i}",
        ))
    return tenant.id, people


async def _build_issued_permit(session, *, tenant_id, foreman_id, supervisor_id):
    """Наряд в issued с foreman+supervisor; личные допуски не нужны (гейт issue не в фокусе)."""
    wp = await svc.create_work_permit(session, tenant_id=tenant_id, work_type="height", zone_text="z")
    await svc.add_member(session, tenant_id=tenant_id, work_permit_id=wp.id, person_id=foreman_id, role="foreman")
    await svc.add_member(session, tenant_id=tenant_id, work_permit_id=wp.id, person_id=supervisor_id, role="supervisor")
    # перевести в issued напрямую (минуя гейт бригады — не предмет теста)
    wp.status = lc.STATUS_ISSUED
    await session.flush()
    return wp


@pytest.mark.asyncio
async def test_record_completion_upsert(sessionmaker, data_factory):
    tid, (foreman, supervisor) = await _persons(data_factory, "Fore", "Super")
    async with sessionmaker() as session:
        wp = await _build_issued_permit(session, tenant_id=tid, foreman_id=foreman.id, supervisor_id=supervisor.id)
        out = await svc.record_completion(
            session, tenant_id=tid, work_permit_id=wp.id,
            completion_text="место сдано", actor_user_id="u1",
        )
        assert out.completion_text == "место сдано"
        assert out.completion_recorded_at is not None
        # идемпотентный upsert
        out2 = await svc.record_completion(
            session, tenant_id=tid, work_permit_id=wp.id,
            completion_text="место сдано-2", actor_user_id="u1",
        )
        assert out2.completion_text == "место сдано-2"


@pytest.mark.asyncio
async def test_record_completion_rejects_non_issued(sessionmaker, data_factory):
    _tid, (person,) = await _persons(data_factory, "Solo")
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(session, tenant_id=person.tenant_id, work_type="height", zone_text="z")
        # статус draft
        with pytest.raises(lc.WorkPermitTransitionError):
            await svc.record_completion(
                session, tenant_id=person.tenant_id, work_permit_id=wp.id,
                completion_text="x", actor_user_id="u1",
            )


@pytest.mark.asyncio
async def test_close_gate_blocks_without_signatures(sessionmaker, data_factory):
    tid, (foreman, supervisor) = await _persons(data_factory, "Fore", "Super")
    async with sessionmaker() as session:
        wp = await _build_issued_permit(session, tenant_id=tid, foreman_id=foreman.id, supervisor_id=supervisor.id)
        await svc.record_completion(
            session, tenant_id=tid, work_permit_id=wp.id, completion_text="готово", actor_user_id="u1",
        )
        with pytest.raises(lc.WorkPermitClosingIncomplete) as ei:
            await svc.close(session, tenant_id=tid, work_permit_id=wp.id, actor_user_id="u1")
        assert "handover_signature" in ei.value.missing
        assert "acceptance_signature" in ei.value.missing


@pytest.mark.asyncio
async def test_close_succeeds_with_act_and_both_signatures(sessionmaker, data_factory):
    tid, (foreman, supervisor) = await _persons(data_factory, "Fore", "Super")
    async with sessionmaker() as session:
        wp = await _build_issued_permit(session, tenant_id=tid, foreman_id=foreman.id, supervisor_id=supervisor.id)
        await svc.record_completion(
            session, tenant_id=tid, work_permit_id=wp.id, completion_text="готово", actor_user_id="u1",
        )
        await sign_closing(session, tenant_id=tid, work_permit_id=wp.id,
                           person_id=foreman.id, mode="attested", requested_by="u1")
        await sign_closing(session, tenant_id=tid, work_permit_id=wp.id,
                           person_id=supervisor.id, mode="attested", requested_by="u1")
        closed = await svc.close(session, tenant_id=tid, work_permit_id=wp.id, actor_user_id="u1")
        assert closed.status == lc.STATUS_CLOSED


@pytest.mark.asyncio
async def test_cancel_not_gated(sessionmaker, data_factory):
    tid, (foreman, supervisor) = await _persons(data_factory, "Fore", "Super")
    async with sessionmaker() as session:
        wp = await _build_issued_permit(session, tenant_id=tid, foreman_id=foreman.id, supervisor_id=supervisor.id)
        cancelled = await svc.cancel(session, tenant_id=tid, work_permit_id=wp.id, actor_user_id="u1")
        assert cancelled.status == lc.STATUS_CANCELLED


@pytest.mark.asyncio
async def test_close_draft_is_transition_error_not_gate(sessionmaker, data_factory):
    _tid, (person,) = await _persons(data_factory, "Solo")
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(session, tenant_id=person.tenant_id, work_type="height", zone_text="z")
        with pytest.raises(lc.WorkPermitTransitionError):
            await svc.close(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")


@pytest.mark.asyncio
async def test_sign_closing_rejects_non_member(sessionmaker, data_factory):
    tid, (foreman, supervisor, outsider) = await _persons(data_factory, "Fore", "Super", "Out")
    async with sessionmaker() as session:
        wp = await _build_issued_permit(session, tenant_id=tid, foreman_id=foreman.id, supervisor_id=supervisor.id)
        with pytest.raises(WorkPermitSignerError):
            await sign_closing(session, tenant_id=tid, work_permit_id=wp.id,
                               person_id=outsider.id, mode="attested", requested_by="u1")


@pytest.mark.asyncio
async def test_sign_closing_rejects_wrong_role(sessionmaker, data_factory):
    """Член бригады с ролью observer не подписывает закрытие."""
    tid, (foreman, supervisor, observer) = await _persons(data_factory, "Fore", "Super", "Obs")
    async with sessionmaker() as session:
        wp = await _build_issued_permit(session, tenant_id=tid, foreman_id=foreman.id, supervisor_id=supervisor.id)
        await svc.add_member(session, tenant_id=tid, work_permit_id=wp.id, person_id=observer.id, role="observer")
        with pytest.raises(WorkPermitSignerError):
            await sign_closing(session, tenant_id=tid, work_permit_id=wp.id,
                               person_id=observer.id, mode="attested", requested_by="u1")


@pytest.mark.asyncio
async def test_sign_closing_double_sign_blocked(sessionmaker, data_factory):
    tid, (foreman, supervisor) = await _persons(data_factory, "Fore", "Super")
    async with sessionmaker() as session:
        wp = await _build_issued_permit(session, tenant_id=tid, foreman_id=foreman.id, supervisor_id=supervisor.id)
        await svc.record_completion(session, tenant_id=tid, work_permit_id=wp.id,
                                    completion_text="готово", actor_user_id="u1")
        await sign_closing(session, tenant_id=tid, work_permit_id=wp.id,
                           person_id=foreman.id, mode="attested", requested_by="u1")
        with pytest.raises(PepConflict):
            await sign_closing(session, tenant_id=tid, work_permit_id=wp.id,
                               person_id=foreman.id, mode="attested", requested_by="u1")
