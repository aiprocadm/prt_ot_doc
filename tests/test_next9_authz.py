# Срез-228: роли `hse_specialist`, `hse_head` и `project_manager` в продукте
# НЕ СУЩЕСТВУЮТ — их убрали из словарей прав вместе с остальными выдуманными.
# Проверки ниже были зелёными ровно потому, что спрашивали несуществующий мир:
# у такой роли прав нет вовсе, и любой отказ подтверждался сам собой. Здесь
# стоят настоящие роли продукта: специалист ОТ, руководитель ОТиПБ, менеджер.
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.rbac_abac import (
    ActorContext,
    actor_from_claims,
    audit_authz_decision,
    policy_engine,
    scoped_query,
)
from app.models.models import AuditLog, Incident, Template


def _actor(
    *,
    roles: list[str],
    company_ids: list[str] | None = None,
    contractor_ids: list[str] | None = None,
) -> ActorContext:
    claims = {
        "sub": str(uuid4()),
        "tenant_id": str(uuid4()),
        "company_ids": company_ids or [],
        "contractor_ids": contractor_ids or [],
    }
    return actor_from_claims(claims, roles)


def test_owner_can_list_documents_across_scope() -> None:
    actor = _actor(roles=["owner"])
    decision = policy_engine.authorize(actor, action="list", resource="documents")
    assert decision.allowed is True


def test_специалисту_ОТ_закрыта_чужая_компания() -> None:
    """Срез-228: роль звалась ``hse_specialist`` — такой в продукте нет.

    Проверка утверждает, что отказ приходит именно от проверки ОБЛАСТИ (чужая
    компания), а не раньше. С выдуманной ролью это не проверялось вовсе: прав у
    неё не было, и до проверки области дело не доходило.
    """

    actor = _actor(roles=["ot_specialist"], company_ids=["cmp-1"])
    obj = SimpleNamespace(company_id="cmp-2")
    decision = policy_engine.authorize(actor, action="read", resource="documents", obj=obj)
    assert decision.allowed is False
    assert decision.reason == "scope_mismatch"


def test_auditor_cannot_update_incident() -> None:
    actor = _actor(roles=["auditor_ro"])
    decision = policy_engine.authorize(actor, action="update", resource="incidents")
    assert decision.allowed is False


def test_client_cannot_access_templates() -> None:
    actor = _actor(roles=["client"])
    decision = policy_engine.authorize(actor, action="read", resource="templates")
    assert decision.allowed is False
    # client has no "templates" module (MODULE_PERMISSIONS["client"]), so the
    # module gate denies first — module_access_denied is the correct reason.
    assert decision.reason in {
        "module_access_denied",
        "client_resource_restricted",
        "missing_permission",
    }


def test_inspector_contractor_reads_within_contractor() -> None:
    actor = _actor(roles=["inspector_contractor"], contractor_ids=["ctr-1"])
    allowed = policy_engine.authorize(
        actor,
        action="read",
        resource="inspections",
        obj=SimpleNamespace(contractor_id="ctr-1"),
    )
    denied = policy_engine.authorize(
        actor,
        action="read",
        resource="inspections",
        obj=SimpleNamespace(contractor_id="ctr-2"),
    )
    assert allowed.allowed is True
    assert denied.allowed is False


def test_scoped_query_filters_company_rows() -> None:
    actor = _actor(roles=["ot_specialist"], company_ids=["cmp-1"])
    stmt = scoped_query(select(Incident), model=Incident, actor=actor, resource="incidents")
    compiled = str(stmt)
    assert "company_id" in compiled


def test_scoped_query_fail_closed_for_scoped_resource_without_columns() -> None:
    actor = _actor(roles=["ot_specialist"], company_ids=["cmp-1"])
    with pytest.raises(Exception):
        scoped_query(select(Template), model=Template, actor=actor, resource="templates")


def test_missing_permission_returns_forbidden_decision() -> None:
    # student has the "training" module but no trainings:delete permission, so this
    # passes the module gate and is denied at the permission layer. (resource=
    # "documents" would deny earlier as module_access_denied — student has no
    # documents module.)
    actor = _actor(roles=["student"])
    decision = policy_engine.authorize(actor, action="delete", resource="trainings")
    assert decision.allowed is False
    assert decision.reason == "missing_permission"


def test_у_каждой_роли_продукта_есть_права() -> None:
    """Срез-228. Здесь стоял список имён, написанный руками: шесть ролей в нём
    не существовали, а одиннадцати настоящих не хватало. Проверка была зелёной
    ровно потому, что спрашивала тот же выдуманный мир.

    Спрашиваем у продукта и у функции, которая знает и словарь, и единую карту
    прав экрана (срез-227).
    """

    from app.core.rbac_abac import permissions_for_role
    from app.models.tenant_billing import RoleEnum

    empty = sorted(role.value for role in RoleEnum if not permissions_for_role(role.value))
    assert not empty, f"роли без единого права: {empty}"


@pytest.mark.anyio("asyncio")
async def test_deny_write_produces_authz_audit_event(sessionmaker) -> None:
    actor = _actor(roles=["auditor_ro"])
    decision = policy_engine.authorize(actor, action="update", resource="incidents")
    assert decision.allowed is False

    async with sessionmaker() as session:
        session.info["tenant"] = "test"
        # Срез-211: сессия и запись аудита должны быть ОДНОГО арендатора. Раньше
        # запись ложилась под арендатора актёра (случайный номер), а читалась
        # сессией без арендатора — расхождение было незаметно. Теперь сессия
        # несёт арендатора, и чужая строка для неё не существует.
        session.info["tenant_id"] = actor.tenant_id
        request = SimpleNamespace(
            url=SimpleNamespace(path="/api/v1/incidents/1"),
            client=SimpleNamespace(host="127.0.0.1"),
        )
        await audit_authz_decision(
            session=session,
            request=request,
            actor=actor,
            resource="incidents",
            action="update",
            decision=decision,
            object_id="1",
        )
        await session.commit()

        rows = (
            (await session.execute(select(AuditLog).where(AuditLog.action == "authz_decision")))
            .scalars()
            .all()
        )
        assert rows
        assert rows[-1].details.get("allowed") is False
