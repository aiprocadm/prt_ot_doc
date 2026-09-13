from __future__ import annotations

from app.api.routes.external_registry import (
    _EXTERNAL_REGISTRY_READ_ROLES,
    _EXTERNAL_REGISTRY_WRITE_ROLES,
)
from app.models.models import RoleEnum


def test_external_registry_access_roles_read_write_parity() -> None:
    read_roles = set(_EXTERNAL_REGISTRY_READ_ROLES)
    write_roles = set(_EXTERNAL_REGISTRY_WRITE_ROLES)

    assert write_roles.issubset(read_roles)
    # Срез-151: прежде тест требовал код `integrations` — роли с таким кодом
    # нет в ``RoleEnum`` и не выдаёт её ничто в продукте (ни пользователи, ни
    # ключи API). Проверка закрепляла мёртвую строку: список обещал доступ,
    # которого не существовало, а тест это охранял. Теперь проверяется то, что
    # имеет смысл, — коды существуют и реестром управляет администрация.
    assert read_roles <= {role.value for role in RoleEnum}
    assert {"admin", "owner"} <= read_roles
