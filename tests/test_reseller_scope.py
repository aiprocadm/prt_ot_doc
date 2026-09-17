"""BIZ-52 срез-2: область видимости флота (разд. 52.1 изоляция, 52.4 кабинет).

Правила чистые — проверяются примерами без базы и без HTTP.
"""

from __future__ import annotations

import pytest

from app.domains.reseller import (
    RESELLER_KIND,
    FleetScope,
    HierarchyViolation,
    TenantLevel,
    TenantNode,
    is_in_scope,
    resolve_fleet_scope,
)

MANAGING = "public"

PLATFORM = TenantNode(id="t-platform", slug="public")
RESELLER = TenantNode(id="t-reseller", slug="partner", kind=RESELLER_KIND)
OTHER_RESELLER = TenantNode(id="t-reseller-2", slug="partner2", kind=RESELLER_KIND)
OWN_CLIENT = TenantNode(id="c1", slug="acme", kind="customer", parent_id="t-reseller")
FOREIGN_CLIENT = TenantNode(id="c2", slug="beta", kind="customer", parent_id="t-reseller-2")
PLATFORM_CLIENT = TenantNode(id="c3", slug="gamma", kind="customer", parent_id=None)


class TestКомуОткрытКабинет:
    def test_владелец_платформы_видит_весь_флот(self) -> None:
        scope = resolve_fleet_scope(PLATFORM, managing_slug=MANAGING)
        assert scope.level is TenantLevel.PLATFORM
        assert scope.owner_id is None
        assert scope.sees_everything

    def test_партнёр_получает_своё_поддерево(self) -> None:
        scope = resolve_fleet_scope(RESELLER, managing_slug=MANAGING)
        assert scope.level is TenantLevel.RESELLER
        assert scope.owner_id == RESELLER.id
        assert not scope.sees_everything

    def test_обычному_арендатору_кабинет_закрыт(self) -> None:
        with pytest.raises(HierarchyViolation) as exc:
            resolve_fleet_scope(OWN_CLIENT, managing_slug=MANAGING)
        assert exc.value.code == "FLEET_ACCESS_FORBIDDEN"

    def test_приостановленный_партнёр_в_кабинет_не_входит(self) -> None:
        suspended = TenantNode(id="t-reseller", slug="partner", kind=RESELLER_KIND, is_active=False)
        with pytest.raises(HierarchyViolation) as exc:
            resolve_fleet_scope(suspended, managing_slug=MANAGING)
        assert exc.value.code == "RESELLER_SUSPENDED"


class TestЧтоВходитВОбласть:
    def test_платформе_принадлежат_все(self) -> None:
        scope = resolve_fleet_scope(PLATFORM, managing_slug=MANAGING)
        for node in (RESELLER, OWN_CLIENT, FOREIGN_CLIENT, PLATFORM_CLIENT):
            assert is_in_scope(scope, node)

    def test_партнёру_принадлежит_свой_клиент(self) -> None:
        scope = resolve_fleet_scope(RESELLER, managing_slug=MANAGING)
        assert is_in_scope(scope, OWN_CLIENT)

    def test_чужой_клиент_не_принадлежит(self) -> None:
        scope = resolve_fleet_scope(RESELLER, managing_slug=MANAGING)
        assert not is_in_scope(scope, FOREIGN_CLIENT)

    def test_клиент_платформы_не_принадлежит_партнёру(self) -> None:
        scope = resolve_fleet_scope(RESELLER, managing_slug=MANAGING)
        assert not is_in_scope(scope, PLATFORM_CLIENT)

    def test_партнёр_не_принадлежит_сам_себе(self) -> None:
        """Иначе партнёр приостановил бы себя и запер собственный кабинет."""

        scope = resolve_fleet_scope(RESELLER, managing_slug=MANAGING)
        assert not is_in_scope(scope, RESELLER)

    def test_соседний_партнёр_не_принадлежит(self) -> None:
        scope = resolve_fleet_scope(RESELLER, managing_slug=MANAGING)
        assert not is_in_scope(scope, OTHER_RESELLER)

    def test_пустой_родитель_не_совпадает_с_пустым_владельцем(self) -> None:
        """Ловушка `None == None`: корневой арендатор не должен «принадлежать» никому.

        Область партнёра всегда несёт непустой ``owner_id``, но проверка обязана
        держаться и на выдуманной области — иначе один неверный конструктор
        отдал бы партнёру всех корневых арендаторов платформы разом.
        """

        broken = FleetScope(level=TenantLevel.RESELLER, owner_id=None)
        assert not is_in_scope(broken, PLATFORM_CLIENT)


class TestКоммерческиеПравки:
    def test_тарифы_и_квоты_пока_только_у_платформы(self) -> None:
        assert resolve_fleet_scope(PLATFORM, managing_slug=MANAGING).may_change_commercials

    def test_партнёру_коммерческие_правки_закрыты(self) -> None:
        """Без потолка «не выдай больше, чем есть у тебя» это раздача за чужой счёт."""

        assert not resolve_fleet_scope(RESELLER, managing_slug=MANAGING).may_change_commercials
