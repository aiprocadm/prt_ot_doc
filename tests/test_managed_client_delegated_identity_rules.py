"""BIZ-49 (разд. 49.3): личность специалиста аутсорсера в контуре клиента.

ЗАЧЕМ. Срез делегированного чтения закрыл сводку по контуру Dedicated-клиента
и честно оставил остаток: интерактивной работы человека ВНУТРИ контура (вход,
запись) не было, потому что строки ``User`` живут в схеме арендатора — личности
у специалиста там просто нет.

Здесь закрепляются РЕШЕНИЯ, а не вёрстка:

1. **адрес личности не может существовать в природе** — иначе письмо ушло бы
   живому человеку, а настоящий сотрудник клиента мог бы занять этот адрес;
2. **у личности нет пароля** — иначе у неё появился бы второй вход, который
   переживёт отзыв гранта и согласия;
3. **административные роли не делегируются** — ведение охраны труда по
   договору не должно давать власть над контуром клиента;
4. **клиент понимает, кто это** — безымянная служебная учётка в своём списке
   пользователей читается как взлом.
"""

from __future__ import annotations

import pytest

from app.domains.managed_clients.delegated_identity import (
    DEFAULT_DELEGATED_ROLE,
    DELEGATED_PASSWORD_MARK,
    delegated_display_name,
    delegated_email,
    delegated_role,
    is_delegated_email,
    is_delegated_password,
)
from app.models.tenant_billing import RoleEnum


def test_адрес_личности_в_зарезервированном_домене() -> None:
    """ГЛАВНОЕ. ``.invalid`` зарезервирован RFC 2606 и не делегируется никому.

    Значит письмо такой личности физически не уйдёт, а настоящий сотрудник
    клиента не сможет занять этот адрес и получить чужие права.
    """

    email = delegated_email(specialist_user_id="u-1", outsourcer_slug="acme")

    assert email.endswith(".invalid")
    assert email == "u-1@acme.delegated.invalid"


def test_адрес_вычисляется_одинаково() -> None:
    """Связь «специалист ↔ его личность» не хранится, а вычисляется.

    Иначе её пришлось бы держать отдельной таблицей, и та однажды разошлась бы
    с тем, что на самом деле лежит в контуре клиента.
    """

    first = delegated_email(specialist_user_id="U-1", outsourcer_slug="Acme")
    second = delegated_email(specialist_user_id="u-1", outsourcer_slug="acme")

    assert first == second


def test_безымянная_личность_не_заводится() -> None:
    with pytest.raises(ValueError):
        delegated_email(specialist_user_id="   ", outsourcer_slug="acme")


def test_делегированная_личность_узнаётся_по_адресу() -> None:
    assert is_delegated_email("u-1@acme.delegated.invalid") is True
    assert is_delegated_email("ivanov@client.ru") is False
    assert is_delegated_email(None) is False


def test_у_личности_нет_пароля() -> None:
    """Метка не похожа на хэш: argon2 и bcrypt всегда начинаются с «$»."""

    assert is_delegated_password(DELEGATED_PASSWORD_MARK) is True
    assert DELEGATED_PASSWORD_MARK.startswith("$") is False
    assert is_delegated_password("$argon2id$v=19$m=65536,t=3,p=4$abc") is False


@pytest.mark.parametrize(
    "role",
    [RoleEnum.OT_SPECIALIST, RoleEnum.OT_PB_LEAD, RoleEnum.PB_ENGINEER, RoleEnum.ECOLOGIST],
)
def test_профессиональная_роль_зеркалится(role: RoleEnum) -> None:
    assert delegated_role(role) is role
    assert delegated_role(role.value) is role


@pytest.mark.parametrize("role", [RoleEnum.OWNER, RoleEnum.ADMIN])
def test_административные_роли_не_делегируются(role: RoleEnum) -> None:
    """ГЛАВНОЕ. В чужом контуре специалист — специалист, а не владелец.

    Владение контуром (пользователи, безопасность, оплата) — дело клиента.
    """

    assert delegated_role(role) is DEFAULT_DELEGATED_ROLE
    assert delegated_role(role) not in {RoleEnum.OWNER, RoleEnum.ADMIN}


def test_незнакомая_роль_опускается_а_не_ломает_вход() -> None:
    """Отказ во входе из-за непонятной роли оставил бы клиента без специалиста."""

    assert delegated_role("такой-роли-нет") is DEFAULT_DELEGATED_ROLE
    assert delegated_role(None) is DEFAULT_DELEGATED_ROLE


def test_имя_называет_чей_это_специалист() -> None:
    """Клиент, открыв список пользователей, обязан понять, кто эти люди."""

    name = delegated_display_name(specialist_name="Иванов И.", outsourcer_name="Ромашка")

    assert "Иванов И." in name
    assert "Ромашка" in name


def test_личность_без_имени_всё_равно_подписана() -> None:
    name = delegated_display_name(specialist_name="", outsourcer_name="")

    assert name.strip() != ""
    assert "аутсорсер" in name
