"""HTTP contract pin for ``/api/v1/operational/dashboard`` (Phase 2.1 closure /
vNext-OPS-01, Session 54).

The operational dashboard route lives in
``backend/app/api/routes/operational_dashboard.py`` and has been wired through
``app.api.v1.route_groups`` since Session 8. ``tests/test_operational_dashboard.py``
covers the service layer plus a happy-path envelope smoke (17 cases), but the
HTTP contract has several gaps the production code already honors and that we
want to lock against future refactors:

- specific status codes when auth or tenant header is missing (the existing
  tests accept any of 400/401/403/404 via ``in`` — too loose to catch a
  regression that flips between them or, worse, starts returning 200);
- the route accepts three header variants
  (``X-Tenant-Id``, ``x-tenant-id``, ``x-tenant``); all three must work or a
  client switching forms will silently break;
- tenant isolation — overdue / unassigned / high-risk aggregates from tenant A
  must not surface in tenant B's dashboard (the single most important
  security invariant of the route);
- RBAC negatives — the route restricts to admin/owner/hr/ot_pb_lead/
  line_manager/manager; ``worker`` must be denied;
- envelope details — ``tenant_id`` echoes the scope header, ``timestamp`` is
  a recent ISO 8601 value, ``status`` is one of four known strings, and the
  ``alert_count`` totals match ``len(alerts)``;
- status-by-severity determination — MEDIUM-only seeds yield ``caution``;
  HIGH seeds yield ``warning``; no seeds yields ``ok``. (No path in the
  current engine produces CRITICAL severity, so the ``critical`` case is
  intentionally unpinned — locking it in today would force the service to
  keep emitting only the four current categories at the four current
  severities forever.)

This file mirrors the contract-pin pattern from
``tests/api/test_webhooks_crud_endpoints.py`` (Session 41),
``tests/api/test_public_api_hardening.py`` (Session 42),
``tests/api/test_pwa_sync_state_machine.py`` (Session 43), and
``tests/api/test_audit_log_api_hardening.py`` (Session 45). No production
code is expected to change — this is a pure contract pin.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    RoleEnum,
    TrainingEnrollment,
    TrainingProgram,
)
from app.models.obligations import Task, TaskStatus
from app.models.risk import Risk
from tests.utils.factories import TestDataFactory

API_PREFIX = "/api/v1"
DASHBOARD_PATH = f"{API_PREFIX}/operational/dashboard"


# =============================================================================
# Helpers
# =============================================================================


def _scope_headers(base: dict[str, str]) -> dict[str, str]:
    """Promote ``x-tenant`` to ``X-Tenant-Id`` so the dashboard route resolves scope.

    The shared ``make_auth_headers`` fixture emits ``x-tenant``; the operational
    dashboard route accepts that alias too, but most production clients send
    ``X-Tenant-Id``, so we exercise the canonical form by default.
    """
    merged = dict(base)
    tid = merged.get("x-tenant") or merged.get("X-Tenant-Id")
    if tid:
        merged.setdefault("X-Tenant-Id", str(tid))
    return merged


async def _admin_for(
    make_auth_headers,
    slug: str,
    *,
    role: RoleEnum = RoleEnum.ADMIN,
) -> dict[str, str]:
    """Issue scoped admin headers for ``slug`` using a per-tenant email.

    Per-tenant email is essential: ``make_auth_headers`` reuses users by global
    email lookup, so a default email reused across tenants returns a user bound
    to the *first* tenant — and the ``rbac`` dependency then 403s on tenant
    mismatch. Distinct emails keep each tenant's user properly bound.
    """
    return await make_auth_headers(
        role,
        tenant=slug,
        email=f"{role.value}-{slug}@opsdash.test",
    )


async def _seed_overdue_training_enrollment(
    session: AsyncSession,
    tenant_id: str,
    *,
    program_code: str = "OPSDASH-OVERDUE",
) -> TrainingEnrollment:
    """Seed one overdue training enrollment → ``OVERDUE`` HIGH alert."""
    program = TrainingProgram(
        tenant_id=tenant_id,
        code=program_code,
        title="Overdue program",
        category="ot",
        kind="course",
        status="active",
    )
    session.add(program)
    await session.flush()

    enrollment = TrainingEnrollment(
        tenant_id=tenant_id,
        training_program_id=program.id,
        person_id=None,
        status="assigned",
        due_at=datetime.now(timezone.utc) - timedelta(days=7),
        assigned_at=datetime.now(timezone.utc) - timedelta(days=30),
        assignment_source="manual",
        progress_percent=0,
        attempt_count=0,
        completion_status="assigned",
    )
    session.add(enrollment)
    await session.flush()
    return enrollment


async def _seed_unassigned_task(
    session: AsyncSession,
    tenant_id: str,
    *,
    title: str,
) -> Task:
    """Seed one open task without assignee → ``UNASSIGNED_TASK`` MEDIUM alert."""
    task = Task(
        tenant_id=tenant_id,
        title=title,
        status=TaskStatus.OPEN,
        assignee_id=None,
    )
    session.add(task)
    await session.flush()
    return task


async def _seed_high_risk(
    session: AsyncSession,
    tenant_id: str,
    *,
    company_id: str,
    level: int = 18,
) -> Risk:
    """Seed one risk register entry with composite level ≥ 15 → ``HIGH_RISK`` HIGH alert."""
    risk = Risk(
        tenant_id=tenant_id,
        company_id=company_id,
        hazard="High-voltage operation under load",
        probability=3,
        severity=5,
        level=level,
    )
    session.add(risk)
    await session.flush()
    return risk


# =============================================================================
# Class A — auth and tenant scope contract (5 cases)
# =============================================================================


@pytest.mark.anyio
class TestOperationalDashboardAuthScope:
    """Auth and tenant scope must be the first guards on the route."""

    async def test_no_auth_returns_unauthenticated_code(
        self, async_client: AsyncClient
    ) -> None:
        """Anonymous request never returns 200 with dashboard data.

        The exact code can be 400/401/403 depending on middleware ordering
        (tenant guard vs bearer guard), but it must never be 200 — that would
        leak alert counts to unauthenticated callers.
        """
        response = await async_client.get(DASHBOARD_PATH)
        assert response.status_code != status.HTTP_200_OK
        assert response.status_code in (
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    async def test_missing_all_tenant_headers_returns_problem_detail(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        """Auth present but every tenant header stripped → 400 with ``TENANT_REQUIRED``.

        The tenant middleware (``app.middleware.tenant.TenantMiddleware``) fires
        before the route handler and emits a structured problem detail; the
        route's own ``{"error": "..."}`` fallback is unreachable in this path.
        Pinning the middleware code keeps clients that match on
        ``code=="TENANT_REQUIRED"`` stable across refactors.
        """
        base = await make_auth_headers(RoleEnum.ADMIN)
        headers = {"Authorization": base["Authorization"]}  # strip every tenant header
        response = await async_client.get(DASHBOARD_PATH, headers=headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        payload = response.json()
        assert payload.get("code") == "TENANT_REQUIRED"
        assert payload.get("type") == "tenancy"
        assert "x-tenant" in str(payload.get("message", "")).lower()

    async def test_x_tenant_uuid_header_alone_resolves_scope(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        """``x-tenant`` is the only header strictly required (per
        ``app.core.tenant.TENANT_HEADER``).

        ``make_auth_headers`` already returns ``x-tenant`` populated with the
        tenant UUID; this test deliberately sends ONLY that header to prove
        the canonical minimal form is sufficient.
        """
        base = await make_auth_headers(RoleEnum.ADMIN)
        headers = {"Authorization": base["Authorization"], "x-tenant": base["x-tenant"]}
        response = await async_client.get(DASHBOARD_PATH, headers=headers)
        assert response.status_code == status.HTTP_200_OK

    async def test_x_tenant_plus_x_tenant_id_redundant_pair_works(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        """Sending both ``x-tenant`` and ``X-Tenant-Id`` with the same UUID is OK.

        The route's ``_tenant_uuid_from_request`` reads from
        ``(X-Tenant-Id, x-tenant-id, x-tenant)`` in order; production clients
        often send both forms for resilience. Pin that redundancy is harmless.
        """
        base = await make_auth_headers(RoleEnum.ADMIN)
        tid = base["x-tenant"]
        headers = {
            "Authorization": base["Authorization"],
            "x-tenant": tid,
            "X-Tenant-Id": tid,
        }
        response = await async_client.get(DASHBOARD_PATH, headers=headers)
        assert response.status_code == status.HTTP_200_OK

    async def test_x_tenant_plus_lowercase_x_tenant_id_pair_works(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        """The lowercase ``x-tenant-id`` variant is also accepted by the route.

        Pin alongside ``X-Tenant-Id``: a refactor that drops one casing from
        the route's three-key search loop would silently break clients still
        sending only the dropped variant.
        """
        base = await make_auth_headers(RoleEnum.ADMIN)
        tid = base["x-tenant"]
        headers = {
            "Authorization": base["Authorization"],
            "x-tenant": tid,
            "x-tenant-id": tid,
        }
        response = await async_client.get(DASHBOARD_PATH, headers=headers)
        assert response.status_code == status.HTTP_200_OK


# =============================================================================
# Class B — response envelope (4 cases)
# =============================================================================


@pytest.mark.anyio
class TestOperationalDashboardEnvelope:
    """The response envelope shape is a public contract — pin its surface."""

    async def test_envelope_required_fields_present(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        response = await async_client.get(
            DASHBOARD_PATH,
            headers=_scope_headers(await make_auth_headers(RoleEnum.ADMIN)),
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        for required in ("tenant_id", "status", "alerts", "alert_count", "timestamp"):
            assert required in data, f"missing envelope field: {required}"
        assert isinstance(data["alerts"], list)
        assert isinstance(data["alert_count"], dict)

    async def test_envelope_status_one_of_known_values(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        response = await async_client.get(
            DASHBOARD_PATH,
            headers=_scope_headers(await make_auth_headers(RoleEnum.ADMIN)),
        )
        assert response.json()["status"] in ("ok", "caution", "warning", "critical")

    async def test_envelope_tenant_id_echoes_scope_header(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        """``tenant_id`` in the response must equal the value passed in the scope header."""
        base = await make_auth_headers(RoleEnum.ADMIN)
        tid = base.get("x-tenant")
        response = await async_client.get(DASHBOARD_PATH, headers=_scope_headers(dict(base)))
        assert response.json()["tenant_id"] == tid

    async def test_envelope_timestamp_iso_and_recent(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        """``timestamp`` is parseable ISO 8601 within a generous 60s window of now."""
        response = await async_client.get(
            DASHBOARD_PATH,
            headers=_scope_headers(await make_auth_headers(RoleEnum.ADMIN)),
        )
        ts_raw = response.json()["timestamp"]
        parsed = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        drift = abs((datetime.now(timezone.utc) - parsed).total_seconds())
        assert drift < 60.0, f"timestamp drift {drift:.1f}s exceeds 60s budget"


# =============================================================================
# Class C — status determination by seeded severity (3 cases)
# =============================================================================


@pytest.mark.anyio
class TestOperationalDashboardStatusDetermination:
    """Verify the ``ok / caution / warning`` ladder under controlled seeds.

    ``critical`` is intentionally unpinned: no current aggregator emits a
    CRITICAL-severity alert, so locking it in would prevent legitimate future
    refactors (e.g. promoting a stale prescription to CRITICAL).
    """

    async def test_status_ok_when_no_alerts_in_tenant(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            await data_factory.ensure_tenant(slug="opsdash-clean", session=session)
            await session.commit()

        headers = _scope_headers(await _admin_for(make_auth_headers, "opsdash-clean"))
        response = await async_client.get(DASHBOARD_PATH, headers=headers)
        data = response.json()
        assert data["status"] == "ok"
        assert data["alerts"] == []

    async def test_status_caution_with_medium_only_seed(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        """One unassigned task → MEDIUM severity → overall ``caution``."""
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(slug="opsdash-medium", session=session)
            await _seed_unassigned_task(session, str(tenant.id), title="medium-only")
            await session.commit()

        headers = _scope_headers(await _admin_for(make_auth_headers, "opsdash-medium"))
        data = (await async_client.get(DASHBOARD_PATH, headers=headers)).json()
        assert data["status"] == "caution"
        assert any(a["category"] == "unassigned_task" for a in data["alerts"])

    async def test_status_warning_with_high_severity_seed(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        """One overdue training enrollment → HIGH severity → overall ``warning``."""
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(slug="opsdash-warning", session=session)
            await _seed_overdue_training_enrollment(session, str(tenant.id))
            await session.commit()

        headers = _scope_headers(await _admin_for(make_auth_headers, "opsdash-warning"))
        data = (await async_client.get(DASHBOARD_PATH, headers=headers)).json()
        assert data["status"] == "warning"


# =============================================================================
# Class D — alert content per category (4 cases)
# =============================================================================


@pytest.mark.anyio
class TestOperationalDashboardAlertContent:
    """Per-category alert shape: severity, category, count, affected_entity_type."""

    async def test_overdue_training_emits_high_overdue_alert(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(slug="opsdash-overdue", session=session)
            await _seed_overdue_training_enrollment(session, str(tenant.id))
            await session.commit()

        headers = _scope_headers(await _admin_for(make_auth_headers, "opsdash-overdue"))
        alerts = (await async_client.get(DASHBOARD_PATH, headers=headers)).json()["alerts"]
        overdue = [a for a in alerts if a["category"] == "overdue"]
        assert overdue, "expected at least one overdue alert"
        first = overdue[0]
        assert first["severity"] == "high"
        assert first["count"] >= 1
        assert first.get("affected_entity_type") == "training_enrollment"

    async def test_unassigned_tasks_aggregate_to_single_medium_alert(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        """Multiple unassigned tasks aggregate into one alert with ``count >= n``."""
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(slug="opsdash-task", session=session)
            await _seed_unassigned_task(session, str(tenant.id), title="t1")
            await _seed_unassigned_task(session, str(tenant.id), title="t2")
            await _seed_unassigned_task(session, str(tenant.id), title="t3")
            await session.commit()

        headers = _scope_headers(await _admin_for(make_auth_headers, "opsdash-task"))
        alerts = (await async_client.get(DASHBOARD_PATH, headers=headers)).json()["alerts"]
        unassigned = [a for a in alerts if a["category"] == "unassigned_task"]
        assert len(unassigned) == 1, "unassigned_task alerts should aggregate, not list each task"
        first = unassigned[0]
        assert first["severity"] == "medium"
        assert first["count"] >= 3
        assert first.get("affected_entity_type") == "task"

    async def test_high_risk_emits_high_alert_with_risk_register_entity(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(slug="opsdash-risk", session=session)
            company = await data_factory.create_company(tenant=tenant, session=session)
            await _seed_high_risk(session, str(tenant.id), company_id=company.id, level=18)
            await session.commit()

        headers = _scope_headers(await _admin_for(make_auth_headers, "opsdash-risk"))
        alerts = (await async_client.get(DASHBOARD_PATH, headers=headers)).json()["alerts"]
        high_risk = [a for a in alerts if a["category"] == "high_risk"]
        assert high_risk, "level≥15 should surface as high_risk alert"
        first = high_risk[0]
        assert first["severity"] == "high"
        assert first["count"] >= 1
        assert first.get("affected_entity_type") == "risk_register"

    async def test_alert_count_sums_match_alerts_length(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        """``sum(alert_count.values()) == len(alerts)`` and severities are within enum."""
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(slug="opsdash-counts", session=session)
            company = await data_factory.create_company(tenant=tenant, session=session)
            await _seed_overdue_training_enrollment(session, str(tenant.id))
            await _seed_unassigned_task(session, str(tenant.id), title="for-count")
            await _seed_high_risk(session, str(tenant.id), company_id=company.id, level=20)
            await session.commit()

        headers = _scope_headers(await _admin_for(make_auth_headers, "opsdash-counts"))
        data = (await async_client.get(DASHBOARD_PATH, headers=headers)).json()
        total_in_counts = sum(int(v) for v in data["alert_count"].values())
        assert total_in_counts == len(data["alerts"])
        for sev_key in data["alert_count"]:
            assert sev_key in ("critical", "high", "medium", "low")


# =============================================================================
# Class E — tenant isolation (2 cases — security-critical)
# =============================================================================


@pytest.mark.anyio
class TestOperationalDashboardTenantIsolation:
    """Per-tenant data must never leak through the dashboard aggregates.

    This is the most security-critical class in the file. A regression dropping
    the ``tenant_id == :tid`` clause from any of the aggregator queries would
    let tenant B observe tenant A's overdue/blocked/risk/task counts.
    """

    async def test_overdue_alerts_do_not_leak_across_tenants(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            tenant_a = await data_factory.ensure_tenant(slug="opsdash-iso-a", session=session)
            await data_factory.ensure_tenant(slug="opsdash-iso-b", session=session)
            await _seed_overdue_training_enrollment(
                session, str(tenant_a.id), program_code="iso-a-overdue"
            )
            await session.commit()

        headers_a = _scope_headers(await _admin_for(make_auth_headers, "opsdash-iso-a"))
        headers_b = _scope_headers(await _admin_for(make_auth_headers, "opsdash-iso-b"))

        alerts_a = (await async_client.get(DASHBOARD_PATH, headers=headers_a)).json()["alerts"]
        alerts_b = (await async_client.get(DASHBOARD_PATH, headers=headers_b)).json()["alerts"]

        assert any(a["category"] == "overdue" for a in alerts_a), (
            "tenant A should see its own overdue alert"
        )
        assert not any(a["category"] == "overdue" for a in alerts_b), (
            "tenant B must NOT see tenant A's overdue alert (cross-tenant leak)"
        )

    async def test_unassigned_tasks_do_not_leak_across_tenants(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            tenant_a = await data_factory.ensure_tenant(slug="opsdash-iso-ta", session=session)
            await data_factory.ensure_tenant(slug="opsdash-iso-tb", session=session)
            await _seed_unassigned_task(session, str(tenant_a.id), title="A-only")
            await session.commit()

        headers_a = _scope_headers(await _admin_for(make_auth_headers, "opsdash-iso-ta"))
        headers_b = _scope_headers(await _admin_for(make_auth_headers, "opsdash-iso-tb"))

        cats_a = [a["category"] for a in (
            await async_client.get(DASHBOARD_PATH, headers=headers_a)
        ).json()["alerts"]]
        cats_b = [a["category"] for a in (
            await async_client.get(DASHBOARD_PATH, headers=headers_b)
        ).json()["alerts"]]

        assert "unassigned_task" in cats_a
        assert "unassigned_task" not in cats_b


# =============================================================================
# Class F — RBAC (3 cases)
# =============================================================================


@pytest.mark.anyio
class TestOperationalDashboardRBAC:
    """Route restricts access to admin/owner/hr/ot_pb_lead/line_manager/manager."""

    async def test_admin_role_allowed(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        response = await async_client.get(
            DASHBOARD_PATH,
            headers=_scope_headers(await make_auth_headers(RoleEnum.ADMIN)),
        )
        assert response.status_code == status.HTTP_200_OK

    async def test_owner_role_allowed(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        response = await async_client.get(
            DASHBOARD_PATH,
            headers=_scope_headers(await make_auth_headers(RoleEnum.OWNER)),
        )
        assert response.status_code == status.HTTP_200_OK

    async def test_worker_role_denied(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        """``worker`` is not in the route's allowlist → ``rbac()`` returns 403."""
        response = await async_client.get(
            DASHBOARD_PATH,
            headers=_scope_headers(await make_auth_headers(RoleEnum.WORKER)),
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
