"""BIZ-61 срез-1 — реестр модулей (Доп. №2, разд. 61.1). Без БД.

Реестр стал источником, из которого выводится продаваемый каталог. Значит
любая правка реестра способна тихо сдвинуть тариф у существующих арендаторов:
код тарифа вычисляется сравнением набора включённых фич с набором плана
(``plan_code_for_features``), и лишняя строка в каталоге делает совпадение
невозможным — арендатор с «Про» внезапно становится «своим набором».

Поэтому тесты стерегут именно границу «реестр ↔ продаваемый каталог».
"""

from __future__ import annotations

from app.modules.subscription.plans import FEATURE_CATALOG, PLANS, plan_code_for_features
from app.modules.subscription.registry import (
    CORE_MODULES,
    MODULE_REGISTRY,
    SELLABLE_MODULES,
    modules_by_category,
)

#: Коды, продаваемые на момент введения реестра. Зафиксированы намеренно:
#: этот набор участвует в сопоставлении тарифов и в гейтах роутеров.
_SELLABLE_AT_INTRODUCTION = {
    "budget",
    "committees",
    "contractors",
    "managed_clients",
    "medical",
    "report_builder",
    "rules_engine",
    "sout",
    "warehouse",
}

#: Что добавлялось в каталог ПОСЛЕ введения реестра — по одной записи на
#: осознанное решение. Список ведётся вручную не из формальности: каждая
#: строка здесь сдвигает тариф «Всё включено» (его набор равен всему
#: каталогу), а значит требует миграции, которая выдаст модуль тем, кто уже
#: купил «всё». Пустая правка этого списка без такой миграции превратила бы
#: живых enterprise-арендаторов в «свой набор».
_SELLABLE_ADDED_LATER = {
    # BIZ-54-57 срез-2 (решение владельца 19.08.2026): дисциплина стала
    # продаваемой. Сдвиг тарифа компенсирует миграция
    # 20260819_fs01_fire_safety_module_grant.
    "fire_safety",
    # Доп. №1 разд. 54.2 срез-1 (24.08.2026): вторая дисциплина получила
    # содержание — реестр ОПО со своими ручками и экраном. Сдвиг тарифа
    # компенсирует миграция 20260824_is01_industrial_safety_module_grant.
    "industrial_safety",
}


def test_sellable_set_changes_only_deliberately() -> None:
    """Каталог = исходный набор плюс ЯВНО объявленные добавления.

    Тест не запрещает расширение — он требует, чтобы расширение было
    записано решением, а не приехало молча вместе с новым модулем.
    """

    assert set(FEATURE_CATALOG) == _SELLABLE_AT_INTRODUCTION | _SELLABLE_ADDED_LATER
    # Пересечение означало бы, что модуль числится и исходным, и добавленным.
    assert not (_SELLABLE_AT_INTRODUCTION & _SELLABLE_ADDED_LATER)


def test_core_modules_are_never_sold() -> None:
    """Ядро нельзя выключить, значит его нельзя и продавать отдельно.

    Попади модуль ядра в каталог — он стал бы фичей тарифа, которую можно
    «не выдать», и арендатор остался бы без документов или без аудита.
    """

    core_codes = {module.code for module in CORE_MODULES}
    assert core_codes & set(FEATURE_CATALOG) == set()
    assert all(module.is_core for module in CORE_MODULES)
    assert not any(module.is_core for module in SELLABLE_MODULES)


def test_plan_matching_still_works() -> None:
    """Тариф обязан узнаваться по набору фич — иначе он станет «своим»."""

    for code, plan in PLANS.items():
        assert plan_code_for_features(set(plan.features)) == code


def test_enterprise_covers_every_sellable_module() -> None:
    """«Всё включено» обязано включать всё продаваемое, иначе это не «всё»."""

    assert set(PLANS["enterprise"].features) == set(FEATURE_CATALOG)


def test_every_module_declares_category_and_routes() -> None:
    """Без категории модуль не найти, без маршрутов — не спрятать (разд. 61.3)."""

    for module in MODULE_REGISTRY:
        assert module.category, f"{module.code}: не указана дисциплина"
        assert module.ui_routes, f"{module.code}: нечего прятать из навигации"
        assert all(route.startswith("/") for route in module.ui_routes), module.code


def test_ui_routes_do_not_overlap_between_modules() -> None:
    """Один экран — один владелец.

    Иначе выключение модуля спрячет чужой раздел, и заказчик потеряет доступ
    к тому, что ему продано.
    """

    seen: dict[str, str] = {}
    for module in MODULE_REGISTRY:
        for route in module.ui_routes:
            assert (
                route not in seen
            ), f"маршрут {route} принадлежит и {seen[route]}, и {module.code}"
            seen[route] = module.code


def test_dependencies_are_declared_and_resolvable() -> None:
    """Зависимость на несуществующий модуль — включение, которое не выполнить."""

    codes = {module.code for module in MODULE_REGISTRY}
    for module in MODULE_REGISTRY:
        for dependency in module.depends_on:
            assert dependency in codes, f"{module.code} зависит от неизвестного {dependency}"
            assert dependency != module.code, f"{module.code} зависит сам от себя"


def test_module_codes_are_unique() -> None:
    codes = [module.code for module in MODULE_REGISTRY]
    assert len(codes) == len(set(codes))


def test_categories_group_the_whole_registry() -> None:
    grouped = modules_by_category()
    assert sum(len(items) for items in grouped.values()) == len(MODULE_REGISTRY)
    assert "Ядро" in grouped
