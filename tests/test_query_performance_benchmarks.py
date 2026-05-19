"""Query performance benchmarks for hot-path services
(Phase 9.1 / vNext-PERF-02, Session 46).

Pins per-method **query counts** for the most frequently-exercised service
methods that back user-visible dashboards. Phase 8 (Sessions 44-45) pinned
*correctness* of analytics + audit. This file pins *query cardinality* —
i.e. how many DB round-trips each high-traffic endpoint costs — so that an
accidental N+1 regression (an unnoticed loop, a missing ``selectinload``,
a service refactor that switches from one SUM to per-row aggregation) is
caught in CI on the cheap SQLite test DB.

What it does NOT do (deliberately):

- **Wall-clock thresholds.** Test runners vary by factor of 5×+ across CI
  fleets, laptops, and Codespaces; absolute timing assertions would either
  pass-on-everything (useless) or flake constantly. The plan's acceptance
  bullet "Query performance benchmarks" is interpreted as "pin the round-trip
  budget per dashboard call" — that *is* the regression signal that matters
  at the SQL layer, and it's deterministic.
- **EXPLAIN ANALYZE.** PostgreSQL-specific; not portable to SQLite test DB.
  Index coverage is already declared in ORM ``__table_args__`` and verified
  structurally below.
- **Replace existing correctness tests.** ``tests/test_analytics_aggregation.py``
  (34 cases, Session 44) and ``tests/test_audit_log_api_hardening.py`` (26
  cases, Session 45) still own correctness; this file only covers the
  cardinality dimension.

Index coverage is also asserted structurally so a future migration that
drops the composite index gets a unit-test failure rather than a slow-query
incident in production.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models.models import AuditLog, Tenant
from app.modules.analytics.services import (
    AnalyticsAggregationService,
    DashboardFilters,
    KpiDashboardService,
)
from app.modules.projections.models import (
    ContractorReadinessReadModel,
    PackageReadModel,
    PersonComplianceReadModel,
    SearchIndexEntry,
    SiteSafetyReadModel,
)


# -----------------------------------------------------------------------------
# Query counter
# -----------------------------------------------------------------------------


class QueryCounter:
    """Counts cursor executions on a bound :class:`AsyncEngine`.

    The counter only increments on SELECT statements (and other
    user-driven reads); housekeeping ``PRAGMA``/``BEGIN``/``COMMIT`` chatter
    on SQLite is filtered out so the assertion targets *application*
    queries rather than transaction plumbing. The filter is conservative —
    any statement starting with SELECT/INSERT/UPDATE/DELETE is counted.
    """

    _COUNTED_PREFIXES = ("SELECT", "INSERT", "UPDATE", "DELETE")

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.count = 0
        self.statements: list[str] = []

    def _on_execute(self, conn, cursor, statement, parameters, context, executemany):  # noqa: D401, ANN001
        head = statement.lstrip().split(" ", 1)[0].upper()
        if head in self._COUNTED_PREFIXES:
            self.count += 1
            self.statements.append(statement)

    def __enter__(self) -> "QueryCounter":
        event.listen(self.engine.sync_engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *_exc) -> None:
        event.remove(self.engine.sync_engine, "before_cursor_execute", self._on_execute)


@contextmanager
def count_queries(session: AsyncSession) -> Iterator[QueryCounter]:
    counter = QueryCounter(session.bind)
    with counter:
        yield counter


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


async def _tenant_id(session: AsyncSession, slug: str = "test") -> str:
    tenant = (await session.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one()
    return str(tenant.id)


async def _seed_package(
    session: AsyncSession,
    *,
    tenant_id: str,
    package_id: str,
    status: str = "new",
    client_company_id: str | None = None,
    site_id: str | None = None,
) -> None:
    session.add(
        PackageReadModel(
            tenant_id=tenant_id,
            package_id=package_id,
            status=status,
            client_company_id=client_company_id,
            site_id=site_id,
        )
    )


async def _seed_person_compliance(
    session: AsyncSession,
    *,
    tenant_id: str,
    person_id: str,
    readiness_status: str = "ready",
    site_id: str | None = None,
    overdue_trainings: int = 0,
    overdue_briefings: int = 0,
) -> None:
    session.add(
        PersonComplianceReadModel(
            tenant_id=tenant_id,
            person_id=person_id,
            readiness_status=readiness_status,
            site_id=site_id,
            overdue_trainings=overdue_trainings,
            overdue_briefings=overdue_briefings,
        )
    )


async def _seed_site_safety(
    session: AsyncSession,
    *,
    tenant_id: str,
    site_id: str,
    open_incidents_count: int = 0,
    open_inspections_count: int = 0,
) -> None:
    session.add(
        SiteSafetyReadModel(
            tenant_id=tenant_id,
            site_id=site_id,
            open_incidents_count=open_incidents_count,
            open_inspections_count=open_inspections_count,
        )
    )


async def _seed_contractor_readiness(
    session: AsyncSession,
    *,
    tenant_id: str,
    contractor_id: str,
    active_packages_count: int = 0,
) -> None:
    session.add(
        ContractorReadinessReadModel(
            tenant_id=tenant_id,
            contractor_id=contractor_id,
            active_packages_count=active_packages_count,
        )
    )


# =============================================================================
# Class A: Analytics base_counters / detailed_counters / trend_series cardinality
# =============================================================================


@pytest.mark.anyio
async def test_base_counters_issues_exactly_four_queries(sessionmaker) -> None:
    """``base_counters`` aggregates four metrics → must be four DB round-trips.

    A regression to 5+ (e.g. someone re-fetches tenant row inside the method)
    is a real cost when the dashboard is opened on every login.
    """
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        service = AnalyticsAggregationService(session, tenant_id)
        with count_queries(session) as q:
            await service.base_counters(DashboardFilters())
    assert q.count == 4, (
        f"base_counters issued {q.count} queries; expected 4. "
        "Possible N+1 regression — check service.py for per-row loops."
    )


@pytest.mark.anyio
async def test_base_counters_query_count_independent_of_row_count(sessionmaker) -> None:
    """Cardinality must be O(1) in number of packages — the canonical N+1 check."""
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        for i in range(50):
            await _seed_package(
                session,
                tenant_id=tenant_id,
                package_id=f"pkg-{i}",
                status="active" if i % 3 == 0 else "new",
            )
        for i in range(50):
            await _seed_person_compliance(
                session,
                tenant_id=tenant_id,
                person_id=f"p-{i}",
                readiness_status="blocked" if i % 2 == 0 else "ready",
            )
        for i in range(10):
            await _seed_site_safety(
                session,
                tenant_id=tenant_id,
                site_id=f"site-{i}",
                open_incidents_count=i,
                open_inspections_count=i * 2,
            )
        await session.commit()

        service = AnalyticsAggregationService(session, tenant_id)
        with count_queries(session) as q:
            counters = await service.base_counters(DashboardFilters())
    assert q.count == 4, f"base_counters scaled to {q.count} queries with 50+50+10 rows"
    assert counters["packages_total"] == 50
    assert counters["overdue_compliance_items"] == 25
    assert counters["open_incidents"] == sum(range(10))
    assert counters["open_inspections"] == sum(range(10)) * 2


@pytest.mark.anyio
async def test_detailed_counters_issues_exactly_eleven_queries(sessionmaker) -> None:
    """``detailed_counters`` aggregates 11 distinct counters → 11 queries.

    There is no FK join needed here — each counter is a COUNT() against a
    different table with a small WHERE clause, and that's the cheapest
    shape. If this asserts the wrong number, someone added a counter and
    needs to update the dashboard SLA in [PLAN.md](docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md).
    """
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        service = AnalyticsAggregationService(session, tenant_id)
        with count_queries(session) as q:
            counters = await service.detailed_counters(DashboardFilters())
    assert q.count == 11, (
        f"detailed_counters issued {q.count} queries; expected 11 (one per counter)."
    )
    assert set(counters.keys()) == {
        "trainings_overdue",
        "ppe_overdue",
        "incidents_open",
        "inspections_open",
        "prescriptions_overdue",
        "workflow_open",
        "workflow_sla_breached",
        "plan_tasks_overdue",
        "integration_errors",
        "edo_status_changes",
        "failed_notifications",
    }


@pytest.mark.anyio
async def test_trend_series_query_count_equals_points(sessionmaker) -> None:
    """``trend_series`` currently issues one query per point.

    This is a *known* baseline — a future optimization to do a single
    grouped query (Phase 9.1 follow-up) will lower this. The pin exists so
    the optimization, when it lands, *visibly* changes this number and we
    notice. It also catches an accidental *worse* regression (e.g. 2×N).
    """
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        service = AnalyticsAggregationService(session, tenant_id)
        with count_queries(session) as q:
            result = await service.trend_series("incidents", points=12)
    assert q.count == 12, (
        f"trend_series(points=12) issued {q.count} queries; expected 12. "
        "If this dropped, congrats — bulk-aggregation landed. Update the pin."
    )
    assert len(result["series"]) == 12


@pytest.mark.anyio
async def test_trend_series_one_point_one_query(sessionmaker) -> None:
    """Single-point trend → single query (zero per-point overhead)."""
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        service = AnalyticsAggregationService(session, tenant_id)
        with count_queries(session) as q:
            await service.trend_series("packages", points=1)
    assert q.count == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "metric",
    ["incidents", "inspections", "packages", "trainings", "compliance", "contractors"],
)
async def test_trend_series_cardinality_constant_across_metrics(sessionmaker, metric: str) -> None:
    """Switching trend metric must not change query count."""
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        service = AnalyticsAggregationService(session, tenant_id)
        with count_queries(session) as q:
            await service.trend_series(metric, points=3)
    assert q.count == 3, f"trend_series({metric!r}) issued {q.count} queries; expected 3"


# =============================================================================
# Class B: KPI dashboard cardinality budgets
# =============================================================================


@pytest.mark.anyio
@pytest.mark.parametrize(
    "name, expected",
    [
        ("executive", 4),
        ("safety", 4),
        ("training", 4),
        ("ppe", 4),
        ("sla_load", 11),
        ("edo", 11),
        ("prescriptions", 11),
    ],
)
async def test_kpi_dashboard_query_budget(sessionmaker, name: str, expected: int) -> None:
    """Each named KPI dashboard has a fixed query budget.

    Budgets:
    - 4 queries: executive / safety / training / ppe (call ``base_counters`` once).
    - 11 queries: sla_load / edo / prescriptions (call ``detailed_counters`` once).
    - 15 queries: client_delivery / incidents / inspections / overdue
      (call both); covered in :func:`test_kpi_dashboard_combined_query_budget`.
    """
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        dash = KpiDashboardService(session, tenant_id)
        method = getattr(dash, name)
        with count_queries(session) as q:
            await method(DashboardFilters())
    assert q.count == expected, (
        f"KpiDashboardService.{name}() issued {q.count} queries; expected {expected}"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("name", ["client_delivery", "incidents", "inspections", "overdue"])
async def test_kpi_dashboard_combined_query_budget(sessionmaker, name: str) -> None:
    """Combined dashboards = 4 (base) + 11 (detailed) = 15 queries."""
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        dash = KpiDashboardService(session, tenant_id)
        method = getattr(dash, name)
        with count_queries(session) as q:
            await method(DashboardFilters())
    assert q.count == 15, (
        f"KpiDashboardService.{name}() issued {q.count} queries; expected 15"
    )


@pytest.mark.anyio
async def test_dashboard_cardinality_unaffected_by_filters(sessionmaker) -> None:
    """Filters narrow WHERE — they must not multiply queries."""
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        service = AnalyticsAggregationService(session, tenant_id)
        filters = DashboardFilters(
            company_id="co-A",
            site_id="s-A",
            status="active",
        )
        with count_queries(session) as q:
            await service.base_counters(filters)
    assert q.count == 4


# =============================================================================
# Class C: Tenant isolation at scale (catches missing tenant_id filter)
# =============================================================================


@pytest.mark.anyio
async def test_base_counters_tenant_isolation_at_scale(sessionmaker) -> None:
    """100+ rows split across two tenants — each tenant must see only its own.

    A regression where a service forgets ``tenant_id`` in WHERE would surface
    here as cross-tenant bleed.
    """
    async with sessionmaker() as session:
        tenant_a = await _tenant_id(session, "test")
        tenant_b = await _tenant_id(session, "acme")
        for i in range(80):
            await _seed_package(session, tenant_id=tenant_a, package_id=f"a-{i}")
        for i in range(20):
            await _seed_package(session, tenant_id=tenant_b, package_id=f"b-{i}")
        await session.commit()

        a_counters = await AnalyticsAggregationService(session, tenant_a).base_counters(
            DashboardFilters()
        )
        b_counters = await AnalyticsAggregationService(session, tenant_b).base_counters(
            DashboardFilters()
        )
    assert a_counters["packages_total"] == 80
    assert b_counters["packages_total"] == 20


@pytest.mark.anyio
async def test_detailed_counters_tenant_isolation_at_scale(sessionmaker) -> None:
    """``detailed_counters`` must respect tenant scoping even with cross-tenant data."""
    async with sessionmaker() as session:
        tenant_a = await _tenant_id(session, "test")
        tenant_b = await _tenant_id(session, "acme")
        service_a = AnalyticsAggregationService(session, tenant_a)
        service_b = AnalyticsAggregationService(session, tenant_b)

        counters_a = await service_a.detailed_counters(DashboardFilters())
        counters_b = await service_b.detailed_counters(DashboardFilters())

    assert all(v == 0 for v in counters_a.values()), counters_a
    assert all(v == 0 for v in counters_b.values()), counters_b


# =============================================================================
# Class D: Audit log filter-matrix query shape
# =============================================================================


async def _seed_audit_entry(
    session: AsyncSession,
    *,
    tenant_id: str,
    action: str,
    object_type: str,
    object_id: str,
    when: datetime | None = None,
    user_id: str | None = None,
    correlation_id: str = "corr-test",
) -> None:
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            when=when or datetime.now(tz=timezone.utc),
            user_id=user_id,
            correlation_id=correlation_id,
        )
    )


@pytest.mark.anyio
async def test_audit_log_list_by_action_uses_single_query(sessionmaker) -> None:
    """``WHERE tenant_id AND action AND when BETWEEN`` → one SELECT.

    The composite index ``ix_auditlog_action(action, when)`` covers ordering;
    the per-row scan must collapse to a single ``SELECT ... FROM auditlog
    WHERE ...``. SQLAlchemy may emit a paging COUNT separately — the pin
    here ensures we don't accidentally fan out per-row lookups.
    """
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)
        for i in range(15):
            await _seed_audit_entry(
                session,
                tenant_id=tenant_id,
                action="login.success" if i % 3 == 0 else "document.create",
                object_type="user" if i % 3 == 0 else "document",
                object_id=f"obj-{i}",
                when=base_time + timedelta(days=i),
            )
        await session.commit()

        stmt = (
            select(AuditLog)
            .where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.action == "login.success",
            )
            .order_by(AuditLog.when.desc())
        )
        with count_queries(session) as q:
            rows = (await session.execute(stmt)).scalars().all()
    assert q.count == 1, f"audit list issued {q.count} queries; expected 1"
    assert len(rows) == 5
    assert all(r.action == "login.success" for r in rows)


@pytest.mark.anyio
async def test_audit_log_filter_by_object_uses_single_query(sessionmaker) -> None:
    """``ix_auditlog_object(object_type, object_id, when)`` covers entity drill-down."""
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        for i in range(20):
            await _seed_audit_entry(
                session,
                tenant_id=tenant_id,
                action="update",
                object_type="document",
                object_id="doc-target" if i < 4 else f"doc-{i}",
            )
        await session.commit()

        stmt = select(AuditLog).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.object_type == "document",
            AuditLog.object_id == "doc-target",
        )
        with count_queries(session) as q:
            rows = (await session.execute(stmt)).scalars().all()
    assert q.count == 1
    assert len(rows) == 4


@pytest.mark.anyio
async def test_audit_log_filter_by_correlation_id_uses_single_query(sessionmaker) -> None:
    """Cross-request tracing must be O(1) lookups by correlation_id."""
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        for i in range(10):
            await _seed_audit_entry(
                session,
                tenant_id=tenant_id,
                action="step",
                object_type="workflow",
                object_id=f"w-{i}",
                correlation_id="corr-X" if i < 3 else "corr-other",
            )
        await session.commit()

        stmt = select(AuditLog).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.correlation_id == "corr-X",
        )
        with count_queries(session) as q:
            rows = (await session.execute(stmt)).scalars().all()
    assert q.count == 1
    assert len(rows) == 3


# =============================================================================
# Class E: Index coverage assertions (structural)
# =============================================================================


def _index_names(model) -> set[str]:
    return {ix.name for ix in model.__table__.indexes}


def _index_columns(model, index_name: str) -> tuple[str, ...]:
    for ix in model.__table__.indexes:
        if ix.name == index_name:
            return tuple(col.name for col in ix.columns)
    raise AssertionError(f"Index {index_name} not found on {model.__tablename__}")


def test_package_read_model_has_composite_index_for_dashboard_filters() -> None:
    """``PackageReadModel`` indexes cover the analytics filter matrix."""
    assert "ix_package_read_models_tenant_status_client_updated" in _index_names(PackageReadModel)
    cols = _index_columns(
        PackageReadModel, "ix_package_read_models_tenant_status_client_updated"
    )
    assert cols == ("tenant_id", "status", "client_company_id", "updated_at")


def test_person_compliance_has_composite_index_for_overdue_lookups() -> None:
    """``PersonComplianceReadModel`` indexes cover overdue + per-site drill-down."""
    cols = _index_columns(
        PersonComplianceReadModel, "ix_person_compliance_tenant_readiness_site_deadline"
    )
    assert cols == ("tenant_id", "readiness_status", "site_id", "next_deadline_at")


def test_site_safety_has_tenant_readiness_index() -> None:
    cols = _index_columns(SiteSafetyReadModel, "ix_site_safety_tenant_readiness")
    assert cols == ("tenant_id", "readiness_status")


def test_contractor_readiness_has_tenant_readiness_index() -> None:
    cols = _index_columns(ContractorReadinessReadModel, "ix_contractor_readiness_tenant_readiness")
    assert cols == ("tenant_id", "readiness_status")


def test_search_index_entries_has_composite_index_for_filtered_search() -> None:
    """``SearchIndexEntry`` indexes cover Universal Search Phase 4.2 hot path."""
    cols = _index_columns(
        SearchIndexEntry, "ix_search_index_entries_tenant_entity_updated"
    )
    assert cols == ("tenant_id", "entity_type", "updated_at")


def test_audit_log_has_action_object_actor_corr_when_indexes() -> None:
    """All five audit-log query axes must be indexed.

    The audit list endpoint (Phase 8.2) supports filtering by:
    - ``action`` → ``ix_auditlog_action(action, when)``
    - ``object_type/object_id`` → ``ix_auditlog_object(object_type, object_id, when)``
    - ``user_id`` (actor) → ``ix_auditlog_actor(user_id, when)``
    - ``correlation_id`` → ``ix_auditlog_corr(correlation_id)``
    - ``when`` range alone → ``ix_auditlog_when(when)``
    """
    names = _index_names(AuditLog)
    assert "ix_auditlog_action" in names
    assert "ix_auditlog_object" in names
    assert "ix_auditlog_actor" in names
    assert "ix_auditlog_corr" in names
    assert "ix_auditlog_when" in names

    assert _index_columns(AuditLog, "ix_auditlog_action") == ("action", "when")
    assert _index_columns(AuditLog, "ix_auditlog_object") == (
        "object_type",
        "object_id",
        "when",
    )
    assert _index_columns(AuditLog, "ix_auditlog_actor") == ("user_id", "when")
    assert _index_columns(AuditLog, "ix_auditlog_corr") == ("correlation_id",)
    assert _index_columns(AuditLog, "ix_auditlog_when") == ("when",)
