"""Срез-147: словарь ролей ``ROLE_LABELS`` полон и не предлагает псевдонимов.

Новая роль в ``RoleEnum`` без подписи показалась бы в выпадающем списке
формы требования латинским кодом — этот тест делает такую забывчивость
красным прогоном.
"""

from __future__ import annotations

from app.core.role_labels import ROLE_ALIASES, ROLE_CODES, ROLE_LABELS, role_label, role_options
from app.models.models import RoleEnum


def test_у_каждой_роли_есть_подпись() -> None:
    missing = [role.value for role in RoleEnum if not ROLE_LABELS.get(role.value, "").strip()]
    assert missing == [], f"роли без подписи: {missing}"
    unknown = set(ROLE_LABELS) - {role.value for role in RoleEnum}
    assert unknown == set(), f"подписи для несуществующих ролей: {unknown}"
    assert ROLE_CODES == {role.value for role in RoleEnum}


def test_псевдонимы_указывают_на_живые_роли_и_не_предлагаются() -> None:
    for alias, target in ROLE_ALIASES.items():
        assert alias in ROLE_CODES and target in ROLE_CODES
        assert target not in ROLE_ALIASES, "псевдоним псевдонима"
    offered = [item["code"] for item in role_options()]
    assert set(offered) == ROLE_CODES - set(ROLE_ALIASES)
    assert len(offered) == len(set(offered))
    assert all(item["label"] == ROLE_LABELS[item["code"]] for item in role_options())


def test_подпись_неизвестного_кода_не_теряется() -> None:
    assert role_label("ot_specialist") == "Специалист ОТ"
    assert role_label("boss") == "boss"
    assert role_label(None) is None
    assert role_label("") is None
