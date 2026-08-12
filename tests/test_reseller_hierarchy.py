"""BIZ-52 срез-1: правила иерархии Platform Owner → Reseller → Client (разд. 52.1).

Правила чистые, поэтому проверяются примерами без базы и без HTTP.
"""

from __future__ import annotations

import pytest

from app.domains.reseller import (
    RESELLER_KIND,
    HierarchyViolation,
    TenantLevel,
    TenantNode,
    inherited_parent_for_spawned_tenant,
    plan_tenant_creation,
    resolve_level,
    validate_parent_candidate,
)

MANAGING = "public"

PLATFORM = TenantNode(id="t-platform", slug="public")
RESELLER = TenantNode(id="t-reseller", slug="partner", kind=RESELLER_KIND)
OTHER_RESELLER = TenantNode(id="t-reseller-2", slug="partner2", kind=RESELLER_KIND)
CLIENT = TenantNode(id="t-client", slug="acme", kind="customer", parent_id="t-reseller")


class TestУровни:
    def test_управляющий_арендатор_это_платформа(self) -> None:
        assert resolve_level(PLATFORM, managing_slug=MANAGING) is TenantLevel.PLATFORM

    def test_платформа_узнаётся_независимо_от_регистра(self) -> None:
        node = TenantNode(id="x", slug="PUBLIC")
        assert resolve_level(node, managing_slug=MANAGING) is TenantLevel.PLATFORM

    def test_вид_reseller_даёт_уровень_реселлера(self) -> None:
        assert resolve_level(RESELLER, managing_slug=MANAGING) is TenantLevel.RESELLER

    def test_обычный_арендатор_это_клиент(self) -> None:
        assert resolve_level(CLIENT, managing_slug=MANAGING) is TenantLevel.CLIENT

    def test_вид_reseller_НЕ_понижает_владельца_платформы(self) -> None:
        """Строка в базе не должна уметь разжаловать владельца в партнёры."""

        disguised = TenantNode(id="t-platform", slug="public", kind=RESELLER_KIND)
        assert resolve_level(disguised, managing_slug=MANAGING) is TenantLevel.PLATFORM


class TestКлиентСоздаватьНеМожет:
    def test_клиент_получает_отказ(self) -> None:
        with pytest.raises(HierarchyViolation) as exc:
            plan_tenant_creation(
                actor=CLIENT,
                requested_kind="customer",
                requested_parent_id=None,
                parent=None,
                managing_slug=MANAGING,
            )
        assert exc.value.code == "TENANT_CREATION_FORBIDDEN"


class TestРеселлер:
    def test_клиент_реселлера_ложится_под_него_даже_без_указания_родителя(self) -> None:
        plan = plan_tenant_creation(
            actor=RESELLER,
            requested_kind="customer",
            requested_parent_id=None,
            parent=None,
            managing_slug=MANAGING,
        )
        assert plan.parent_id == RESELLER.id
        assert plan.kind == "customer"

    def test_реселлер_не_может_создать_реселлера(self) -> None:
        with pytest.raises(HierarchyViolation) as exc:
            plan_tenant_creation(
                actor=RESELLER,
                requested_kind=RESELLER_KIND,
                requested_parent_id=None,
                parent=None,
                managing_slug=MANAGING,
            )
        assert exc.value.code == "RESELLER_CANNOT_CREATE_RESELLER"

    def test_реселлер_не_может_завести_клиента_в_чужом_контуре(self) -> None:
        with pytest.raises(HierarchyViolation) as exc:
            plan_tenant_creation(
                actor=RESELLER,
                requested_kind="customer",
                requested_parent_id=OTHER_RESELLER.id,
                parent=OTHER_RESELLER,
                managing_slug=MANAGING,
            )
        assert exc.value.code == "RESELLER_PARENT_MISMATCH"

    def test_явное_указание_себя_родителем_допустимо(self) -> None:
        plan = plan_tenant_creation(
            actor=RESELLER,
            requested_kind="customer",
            requested_parent_id=RESELLER.id,
            parent=RESELLER,
            managing_slug=MANAGING,
        )
        assert plan.parent_id == RESELLER.id

    def test_приостановленный_реселлер_не_заводит_клиентов(self) -> None:
        suspended = TenantNode(
            id="t-reseller", slug="partner", kind=RESELLER_KIND, is_active=False
        )
        with pytest.raises(HierarchyViolation) as exc:
            plan_tenant_creation(
                actor=suspended,
                requested_kind="customer",
                requested_parent_id=None,
                parent=None,
                managing_slug=MANAGING,
            )
        assert exc.value.code == "RESELLER_SUSPENDED"


class TestВладелецПлатформы:
    def test_создаёт_реселлера_корнем(self) -> None:
        plan = plan_tenant_creation(
            actor=PLATFORM,
            requested_kind=RESELLER_KIND,
            requested_parent_id=None,
            parent=None,
            managing_slug=MANAGING,
        )
        assert plan.kind == RESELLER_KIND
        assert plan.parent_id is None

    def test_реселлер_с_родителем_отвергается(self) -> None:
        with pytest.raises(HierarchyViolation) as exc:
            plan_tenant_creation(
                actor=PLATFORM,
                requested_kind=RESELLER_KIND,
                requested_parent_id=RESELLER.id,
                parent=RESELLER,
                managing_slug=MANAGING,
            )
        assert exc.value.code == "RESELLER_MUST_BE_ROOT"

    def test_свой_клиент_создаётся_без_родителя(self) -> None:
        plan = plan_tenant_creation(
            actor=PLATFORM,
            requested_kind="customer",
            requested_parent_id=None,
            parent=None,
            managing_slug=MANAGING,
        )
        assert plan.parent_id is None

    def test_клиента_можно_отдать_реселлеру(self) -> None:
        plan = plan_tenant_creation(
            actor=PLATFORM,
            requested_kind="customer",
            requested_parent_id=RESELLER.id,
            parent=RESELLER,
            managing_slug=MANAGING,
        )
        assert plan.parent_id == RESELLER.id

    def test_ненайденный_родитель_не_превращается_в_корень(self) -> None:
        """Опечатка в id обязана падать, а не создавать арендатора платформы."""

        with pytest.raises(HierarchyViolation) as exc:
            plan_tenant_creation(
                actor=PLATFORM,
                requested_kind="customer",
                requested_parent_id="нет-такого",
                parent=None,
                managing_slug=MANAGING,
            )
        assert exc.value.code == "TENANT_PARENT_NOT_FOUND"


class TestОбходныеПути:
    def test_регистр_и_пробелы_не_обходят_запрет(self) -> None:
        """`" ReSeller "` — это тот же уровень, а не новый вид."""

        with pytest.raises(HierarchyViolation) as exc:
            plan_tenant_creation(
                actor=RESELLER,
                requested_kind=" ReSeller ",
                requested_parent_id=None,
                parent=None,
                managing_slug=MANAGING,
            )
        assert exc.value.code == "RESELLER_CANNOT_CREATE_RESELLER"

    def test_платформа_не_назначает_родителем_саму_себя(self) -> None:
        with pytest.raises(HierarchyViolation) as exc:
            plan_tenant_creation(
                actor=PLATFORM,
                requested_kind="customer",
                requested_parent_id=PLATFORM.id,
                parent=PLATFORM,
                managing_slug=MANAGING,
            )
        assert exc.value.code == "TENANT_PARENT_IS_PLATFORM"

    def test_вид_по_умолчанию_подставляется_если_не_указан(self) -> None:
        plan = plan_tenant_creation(
            actor=RESELLER,
            requested_kind="",
            requested_parent_id=None,
            parent=None,
            managing_slug=MANAGING,
        )
        assert plan.kind == "customer"


class TestКтоГодитсяВРодители:
    def test_клиент_родителем_быть_не_может(self) -> None:
        with pytest.raises(HierarchyViolation) as exc:
            validate_parent_candidate(CLIENT, managing_slug=MANAGING)
        assert exc.value.code == "TENANT_PARENT_NOT_RESELLER"

    def test_платформа_родителем_не_указывается(self) -> None:
        with pytest.raises(HierarchyViolation) as exc:
            validate_parent_candidate(PLATFORM, managing_slug=MANAGING)
        assert exc.value.code == "TENANT_PARENT_IS_PLATFORM"

    def test_приостановленный_реселлер_не_принимает_клиентов(self) -> None:
        suspended = TenantNode(id="r", slug="p", kind=RESELLER_KIND, is_active=False)
        with pytest.raises(HierarchyViolation) as exc:
            validate_parent_candidate(suspended, managing_slug=MANAGING)
        assert exc.value.code == "RESELLER_SUSPENDED"


class TestАрендаторРождённыйКонтуром:
    """BIZ-49: перевод Managed Client в собственный контур создаёт арендатора."""

    def test_у_платформы_рождается_корневой(self) -> None:
        assert inherited_parent_for_spawned_tenant(PLATFORM, managing_slug=MANAGING) is None

    def test_у_реселлера_рождается_под_реселлером(self) -> None:
        assert (
            inherited_parent_for_spawned_tenant(RESELLER, managing_slug=MANAGING) == RESELLER.id
        )

    def test_у_клиента_реселлера_дед_не_меняется(self) -> None:
        """Четвёртого уровня не появляется: подопечный остаётся у того же партнёра."""

        assert (
            inherited_parent_for_spawned_tenant(CLIENT, managing_slug=MANAGING) == RESELLER.id
        )

    def test_у_клиента_платформы_рождается_корневой(self) -> None:
        own = TenantNode(id="c", slug="acme", kind="customer", parent_id=None)
        assert inherited_parent_for_spawned_tenant(own, managing_slug=MANAGING) is None
