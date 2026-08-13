"""BIZ-52 срез-8: потолок партнёра при тарификации клиентов (разд. 52.4).

Правила чистые — проверяются наборами кодов без базы.
"""

from __future__ import annotations

from app.domains.reseller.subbilling import check_plan_ceiling, is_ceiling_applicable


class TestПотолокНабора:
    def test_тариф_внутри_набора_партнёра_проходит(self) -> None:
        verdict = check_plan_ceiling(
            plan_features={"sout", "medical"},
            reseller_features={"sout", "medical", "ppe"},
        )
        assert verdict.allowed
        assert verdict.missing == ()
        assert verdict.reason == ""

    def test_совпадающий_набор_проходит(self) -> None:
        verdict = check_plan_ceiling(
            plan_features={"sout"}, reseller_features={"sout"}
        )
        assert verdict.allowed

    def test_лишний_модуль_не_выдаётся(self) -> None:
        verdict = check_plan_ceiling(
            plan_features={"sout", "ppe"}, reseller_features={"sout"}
        )
        assert not verdict.allowed
        assert verdict.missing == ("ppe",)
        assert "ppe" in verdict.reason

    def test_недостающие_модули_отсортированы(self) -> None:
        """Одинаковая причина обязана давать одинаковое сообщение.

        Иначе его нельзя ни закрепить тестом, ни узнать в поддержке.
        """

        verdict = check_plan_ceiling(
            plan_features={"ppe", "sout", "medical"}, reseller_features=set()
        )
        assert verdict.missing == ("medical", "ppe", "sout")

    def test_пустой_тариф_проходит_при_пустом_наборе(self) -> None:
        """«Бесплатный» тариф не требует от партнёра ничего."""

        verdict = check_plan_ceiling(plan_features=set(), reseller_features=set())
        assert verdict.allowed

    def test_партнёр_без_набора_ничего_не_выдаёт(self) -> None:
        verdict = check_plan_ceiling(
            plan_features={"sout"}, reseller_features=set()
        )
        assert not verdict.allowed


class TestКомуПотолокНужен:
    def test_владельцу_платформы_потолок_не_применяется(self) -> None:
        """Он источник модулей: ограничивать его собственным набором бессмысленно."""

        assert not is_ceiling_applicable(actor_sees_everything=True)

    def test_партнёру_потолок_применяется(self) -> None:
        assert is_ceiling_applicable(actor_sees_everything=False)
