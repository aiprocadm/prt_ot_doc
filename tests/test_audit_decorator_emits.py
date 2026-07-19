"""``@audit_operation`` must actually write a row -- on every decorated handler.

The immutability of an audit entry is pinned in
``tests/test_audit_log_immutability.py``; the hash chain in
``tests/test_audit_chain_and_diff.py``. Neither asserts that an entry is
*created*, which is how 193 of 249 decorated handlers came to audit into the
void: FastAPI only passes parameters a handler declares, the decorator required
``request``, and handlers that omitted it took the early return. Every guard
protected the row and none protected its existence.

So the assertions here deliberately drive a handler that does NOT declare
``request`` (``POST /api/v1/ppe/suppliers``) and read the audit table back
through a SEPARATE session.
"""

from __future__ import annotations

import ast
import pathlib

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.feature import Feature, FeatureEnablement
from app.models.models import RoleEnum
from app.models.ppe import PPESupplier
from tests.utils.factories import TestDataFactory

_APP_ROOT = pathlib.Path(__file__).resolve().parents[1] / "backend" / "app"


def _decorated_handlers() -> list[tuple[str, str, list[str]]]:
    """Every ``@audit_operation``-decorated function as (file, name, params)."""

    found: list[tuple[str, str, list[str]]] = []
    for path in sorted(_APP_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensive
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            if not any("audit_operation" in ast.unparse(d) for d in node.decorator_list):
                continue
            params = [a.arg for a in node.args.args + node.args.kwonlyargs]
            found.append((str(path.relative_to(_APP_ROOT)), node.name, params))
    return found


def test_every_decorated_handler_can_emit() -> None:
    """``session`` is the one parameter the decorator still cannot do without.

    ``request`` is resolved from the ASGI scope, but the entry has to be written
    in the handler's own transaction, so the session must be injected. A handler
    missing it is decorated-but-mute -- exactly the defect this module guards.
    """

    handlers = _decorated_handlers()
    assert handlers, "found no @audit_operation handlers -- the AST scan is broken"

    mute = [f"{path}::{name}" for path, name, params in handlers if "session" not in params]
    assert not mute, (
        "these handlers are decorated with @audit_operation but take no `session`, "
        "so they can never write an audit entry: " + ", ".join(mute)
    )


async def _enable_warehouse(sessionmaker, data_factory: TestDataFactory) -> None:
    """Mirrors ``tests/api/test_ppe_persistence_regression.py``."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        feature = (
            await session.execute(select(Feature).where(Feature.code == "warehouse"))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="warehouse", title="Warehouse")
            session.add(feature)
            await session.flush()
        session.add(FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=True))
        await session.commit()


@pytest.mark.asyncio
async def test_handler_without_request_parameter_still_audits(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    """The regression itself: ``create_supplier_endpoint`` declares no ``request``."""

    await _enable_warehouse(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    resp = await async_client.post(
        "/api/v1/ppe/suppliers", json={"name": "ООО Аудит"}, headers=headers
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    supplier_id = resp.json()["id"]

    async with sessionmaker() as fresh:
        rows = (
            (
                await fresh.execute(
                    select(AuditLog).where(
                        AuditLog.object_type == "ppe_supplier",
                        AuditLog.object_id == supplier_id,
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == 1, (
        "POST /ppe/suppliers wrote no audit entry -- the handler declares no "
        "`request` parameter, so the decorator took its early return"
    )
    entry = rows[0]
    assert entry.action == "create"
    assert entry.user_id is not None, "the acting user was not attributed"
    assert entry.ip, "the client IP was not attributed"


@pytest.mark.asyncio
async def test_failed_audit_write_does_not_discard_the_business_row(
    async_client: AsyncClient,
    make_auth_headers,
    sessionmaker,
    data_factory: TestDataFactory,
    monkeypatch,
):
    """A rejected audit insert must not take the request down with it.

    Auditing runs inside the handler's transaction, so without a SAVEPOINT a
    failed insert would leave that transaction aborted and the commit in
    ``transaction_scope`` would raise -- converting a successful write into a
    500 and losing the row.
    """

    await _enable_warehouse(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    from app.services import audit as audit_module

    async def _boom(self, **kwargs):  # noqa: ANN001, ANN003
        raise RuntimeError("audit backend is down")

    monkeypatch.setattr(audit_module.AuditService, "log_event", _boom)

    resp = await async_client.post(
        "/api/v1/ppe/suppliers", json={"name": "ООО Стойкость"}, headers=headers
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    supplier_id = resp.json()["id"]

    async with sessionmaker() as fresh:
        row = await fresh.get(PPESupplier, supplier_id)

    assert row is not None, "a failing audit write rolled back the business row"
    assert row.name == "ООО Стойкость"
