"""SEC-63.1: кого затронет приостановка (Доп. №3 разд. 63.1, четвёртая угроза).

Правила чистые — проверяются списками узлов без базы.
"""

from __future__ import annotations

from app.domains.reseller.cascade import plan_suspension_cascade
from app.domains.reseller.hierarchy import RESELLER_KIND, TenantNode

PARTNER = TenantNode(id="r1", slug="partner", kind=RESELLER_KIND)
CLIENT = TenantNode(id="c9", slug="acme", kind="customer", parent_id=None)


def _child(slug: str, parent: str = "r1", active: bool = True) -> TenantNode:
    return TenantNode(id=f"id-{slug}", slug=slug, kind="customer", parent_id=parent,
                      is_active=active)


class TestКогоЗатрагивает:
    def test_клиенты_партнёра_попадают_в_список(self) -> None:
        impact = plan_suspension_cascade(
            PARTNER, children=[_child("acme"), _child("beta")], activating=False
        )
        assert impact.affected == ("acme", "beta")
        assert impact.count == 2

    def test_чужие_клиенты_не_попадают(self) -> None:
        """Ребёнок другого партнёра не должен считаться затронутым."""

        impact = plan_suspension_cascade(
            PARTNER,
            children=[_child("acme"), _child("gamma", parent="r2")],
            activating=False,
        )
        assert impact.affected == ("acme",)

    def test_уже_приостановленный_клиент_тоже_затронут(self) -> None:
        """Считать только активных значило бы занизить число.

        Клиент остаётся клиентом партнёра и в приостановленном состоянии, а
        режим чтения вычисляется на лету из статуса партнёра.
        """

        impact = plan_suspension_cascade(
            PARTNER, children=[_child("acme", active=False)], activating=False
        )
        assert impact.affected == ("acme",)

    def test_список_отсортирован(self) -> None:
        """Одинаковое действие обязано давать одинаковую запись в аудите."""

        impact = plan_suspension_cascade(
            PARTNER,
            children=[_child("яблоко"), _child("acme"), _child("beta")],
            activating=False,
        )
        assert list(impact.affected) == sorted(impact.affected)


class TestУОбычногоАрендатораКаскадаНет:
    def test_не_партнёр_не_даёт_каскада(self) -> None:
        impact = plan_suspension_cascade(
            CLIENT, children=[_child("x", parent="c9")], activating=False
        )
        assert impact.is_reseller is False
        assert impact.count == 0

    def test_текст_различает_ноль_и_отсутствие_каскада(self) -> None:
        """«Каскад пуст» и «каскада нет» — разные вещи, и читаться должны по-разному."""

        no_cascade = plan_suspension_cascade(CLIENT, children=[], activating=False)
        empty_cascade = plan_suspension_cascade(PARTNER, children=[], activating=False)

        assert no_cascade.summary != empty_cascade.summary
        assert "не партнёр" in no_cascade.summary
        assert "нет клиентов" in empty_cascade.summary


class TestВозобновлениеТожеПрослеживается:
    def test_состав_затронутых_один_и_тот_же(self) -> None:
        """Обе стороны каскада обязаны быть одинаково видны в журнале."""

        children = [_child("acme"), _child("beta")]
        off = plan_suspension_cascade(PARTNER, children=children, activating=False)
        on = plan_suspension_cascade(PARTNER, children=children, activating=True)

        assert off.affected == on.affected
