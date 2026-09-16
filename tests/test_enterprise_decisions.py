"""BIZ-53 разд. 53.3: решения по enterprise-аренде названы и не молчат.

ЗАЧЕМ. Разд. 53.3 перечисляет, что нужно крупному заказчику. Часть сделана,
часть сделана НАМЕРЕННО ИНАЧЕ, часть не делается кодом вообще. Пока такие
решения живут только в отчётах, происходит одно из двух: их забывают и делают
заново, либо заказчику обещают то, чего нет.

Здесь закрепляется не текст реестра, а его СВОЙСТВА:

1. **полнота** — каждое требование разд. 53.3 в реестре есть; забытая строка
   всплывает не здесь, а на переговорах словами «мы думали, это есть»;
2. **состояния три, четвёртого нет** — «пока не решили» не состояние;
3. **у отказа названы ПРИЧИНА и ЧТО ДЕЛАТЬ** — «не поддерживаем» без
   продолжения означает для заказчика «идите к конкуренту»;
4. **у сделанного указано, где смотреть** — иначе «сделано» проверить нечем;
5. **реестр РАБОТАЕТ** — отказ настройки единого входа печатает причину и
   обходной путь прямо из него, а не своими словами, которые разойдутся.
"""

from __future__ import annotations

import pytest

from app.domains.enterprise.decisions import (
    BY_DEPLOYMENT,
    DECLINED,
    DONE,
    ENTERPRISE_DECISIONS,
    decision_for,
)

#: Требования разд. 53.3 Доп. №1 — переписаны из ТЗ, а не из реестра.
#: Сверять реестр с самим собой бессмысленно: так пропажа не видна.
REQUIRED_KEYS = {
    "onboarding",
    "isolation",
    "sso",
    "saml",
    "ldap",
    "integration_1c",
    "integration_hr",
    "integration_bi",
    "sla",
    "dpa",
    "group_hierarchy",
}


def test_все_требования_раздела_53_3_имеют_решение() -> None:
    """ГЛАВНОЕ. Требование без решения всплывает на переговорах, а не в коде."""

    assert {item.key for item in ENTERPRISE_DECISIONS} == REQUIRED_KEYS


def test_состояний_три_и_четвёртого_нет() -> None:
    """«Пока не решили» — не состояние: именно оно и теряется."""

    assert {item.state for item in ENTERPRISE_DECISIONS} <= {DONE, BY_DEPLOYMENT, DECLINED}


def test_ключи_не_повторяются() -> None:
    keys = [item.key for item in ENTERPRISE_DECISIONS]

    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("item", [i for i in ENTERPRISE_DECISIONS if i.state == DECLINED])
def test_у_отказа_есть_причина_и_обходной_путь(item) -> None:
    """«Не поддерживаем» без продолжения читается как «идите к конкуренту»."""

    assert len(item.reason) > 40, f"{item.key}: причина отказа не названа"
    assert len(item.workaround) > 20, f"{item.key}: не сказано, что делать вместо"


@pytest.mark.parametrize("item", [i for i in ENTERPRISE_DECISIONS if i.state == DONE])
def test_у_сделанного_указано_где_смотреть(item) -> None:
    """«Сделано» без адреса проверить нечем — и через год никто не вспомнит."""

    assert item.evidence, f"{item.key}: не сказано, где смотреть"


@pytest.mark.parametrize("item", ENTERPRISE_DECISIONS)
def test_требование_переписано_из_тз(item) -> None:
    """Реестр сверяется с ТЗ, а не с памятью: формулировка хранится рядом."""

    assert len(item.requirement) > 10


def test_каталог_отвечает_по_ключу_и_не_выдумывает() -> None:
    assert decision_for("SAML") is not None
    assert decision_for("saml").supported is False
    assert decision_for("sso").supported is True
    assert decision_for("такого-нет") is None


def test_реестр_действительно_работает_в_отказе_настройки_входа() -> None:
    """ГЛАВНОЕ ПРО СВЯЗЬ. Реестр не украшение: отказ печатает ЕГО слова.

    Своими словами отказ однажды разошёлся бы с решением, и заказчик услышал
    бы две разные версии от платформы и от менеджера.
    """

    from app.schemas.sso import SsoConfigWrite

    with pytest.raises(ValueError) as exc:
        SsoConfigWrite(provider="saml")

    message = str(exc.value)
    decision = decision_for("saml")
    assert decision.reason in message, "отказ не назвал причину из реестра"
    assert decision.workaround in message, "отказ не сказал, что делать вместо"


def test_ldap_тоже_объяснён_а_не_отвергнут_молча() -> None:
    from app.schemas.sso import SsoConfigWrite

    with pytest.raises(ValueError) as exc:
        SsoConfigWrite(provider="ldap")

    assert decision_for("ldap").workaround in str(exc.value)


def test_незнакомое_значение_остаётся_обычной_ошибкой() -> None:
    """Обратная сторона: объяснять надо РЕШЕНИЯ, а не любую опечатку."""

    from app.schemas.sso import SsoConfigWrite

    with pytest.raises(ValueError) as exc:
        SsoConfigWrite(provider="абырвалг")

    assert "не поддерживается осознанно" not in str(exc.value)
