"""BIZ-53 срез-2: редакции под размер заказчика (Доп. №1 разд. 53.1).

ТЗ даёт таблицу из четырёх редакций с ЯВНЫМИ профилями заказчика. В коде были
три технических тарифа с подписями «Базовый / Про / Всё включено» — по ним
заказчик не может понять, что выбрать.

Здесь закреплено то, что легко потерять правкой:

* все четыре редакции ТЗ на месте и у каждой назван профиль заказчика;
* редакция ссылается на СУЩЕСТВУЮЩИЙ тариф — иначе продавали бы пустоту;
* каждый тариф продаётся хотя бы одной редакцией — иначе тариф недостижим в
  продаже и о нём никто не узнает;
* **две редакции на одном тарифе обязаны объяснить, чем отличаются** — иначе
  это две строки прайса, отличающиеся только именем.
"""

from __future__ import annotations

import pytest

from app.modules.subscription.editions import (
    EDITIONS,
    PLANS_WITHOUT_EDITION,
    edition_by_code,
    editions_for_plan,
)
from app.modules.subscription.plans import PLANS, plan_code_for_features

#: Коды из таблицы разд. 53.1 — сверяемся со СТРОКАМИ ТЗ, а не с числом.
TZ_EDITIONS = {
    "start_ot": "Start OT",
    "business_ot": "Business OT",
    "safety_suite": "Safety Suite",
    "enterprise_holding": "Enterprise Holding",
}


class TestТаблицаТЗ:
    def test_все_четыре_редакции_на_месте(self) -> None:
        assert {item.code: item.title for item in EDITIONS} == TZ_EDITIONS

    @pytest.mark.parametrize("edition", EDITIONS, ids=lambda e: e.code)
    def test_у_редакции_назван_профиль_заказчика(self, edition) -> None:
        """Без профиля редакция снова становится набором флагов.

        Именно этим и были плохи «Базовый / Про / Всё включено»: они говорят о
        составе, а не о том, кому подходят.
        """

        assert edition.audience.strip(), edition.code

    @pytest.mark.parametrize("edition", EDITIONS, ids=lambda e: e.code)
    def test_у_редакции_сказано_что_входит(self, edition) -> None:
        assert edition.includes.strip(), edition.code


class TestСвязьСТарифами:
    @pytest.mark.parametrize("edition", EDITIONS, ids=lambda e: e.code)
    def test_тариф_редакции_существует(self, edition) -> None:
        """Ссылка на несуществующий тариф означала бы продажу пустоты."""

        assert edition.plan_code in PLANS, edition.code

    def test_каждый_тариф_продаётся_хотя_бы_одной_редакцией(self) -> None:
        """Тариф без редакции недостижим в продаже — о нём никто не узнает."""

        assert PLANS_WITHOUT_EDITION == frozenset()

    def test_редакции_покрывают_все_тарифы(self) -> None:
        assert {item.plan_code for item in EDITIONS} == set(PLANS)


class TestДвойникиОбъясняются:
    """Главный сторож среза: две редакции на одном тарифе — не переименование."""

    def test_общий_тариф_обязан_быть_объяснён(self) -> None:
        """Сопоставление тарифа идёт по ТОЧНОМУ набору модулей и возвращает
        ПЕРВЫЙ подходящий — два тарифа с одинаковым набором неразличимы. Поэтому
        Enterprise Holding и не может быть отдельным тарифом; но раз он делит
        тариф с Safety Suite, он ОБЯЗАН сказать словами, чем отличается."""

        for plan_code in {item.plan_code for item in EDITIONS}:
            shared = editions_for_plan(plan_code)
            if len(shared) < 2:
                continue
            explained = [item for item in shared if item.beyond_modules.strip()]
            assert len(explained) >= len(shared) - 1, (
                f"тариф {plan_code}: редакций {len(shared)}, " f"объяснена только {len(explained)}"
            )

    def test_enterprise_holding_объясняет_отличие_условиями(self) -> None:
        holding = edition_by_code("enterprise_holding")
        assert holding is not None
        # Разд. 53.3 перечисляет именно условия, а не модули.
        for word in ("SSO", "SLA", "изоляц"):
            assert word in holding.beyond_modules, word

    def test_редакция_с_личным_тарифом_объяснений_не_требует(self) -> None:
        """Обратная половина: пустое поле — норма там, где тариф свой."""

        for code in ("start_ot", "business_ot"):
            edition = edition_by_code(code)
            assert edition is not None and edition.beyond_modules == ""


class TestТарифыНеСломались:
    def test_сопоставление_по_модулям_осталось_однозначным(self) -> None:
        """Срез добавляет продуктовый слой и НЕ трогает набор тарифов: иначе
        существующий арендатор перестал бы совпадать с пресетом и увидел бы
        «Свой набор» вместо своей редакции (ловушка BIZ-54-57 среза-2)."""

        for code, plan in PLANS.items():
            assert plan_code_for_features(set(plan.features)) == code
