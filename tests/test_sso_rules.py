"""Единый вход: правила без сети и без базы (BIZ-53 разд. 53.3, срез-204).

ЧТО БЫЛО. Разд. 53.3 требует для enterprise-аренды «SSO/SAML/LDAP», задача
P10-13 дорожной карты стояла «не начато». Сотрудник крупного заказчика заводил в
платформе ЕЩЁ ОДИН пароль, а служба безопасности заказчика не могла ни отозвать
доступ централизованно, ни потребовать своей двухфакторности.

ЗДЕСЬ ПРОВЕРЯЮТСЯ РЕШЕНИЯ, А НЕ ПРОВОДА. Три из них дороже остального:

1. **Пустой список доменов — запрет всем, а не «можно всем».** «Пусто значит
   всё» выглядит удобно ровно до первой забытой настройки, после которой в
   контур заказчика входит кто угодно с любой почтой, которую подпишет его
   провайдер.
2. **Неподтверждённый адрес не принимается.** В чужом каталоге адрес мог вписать
   сам пользователь — тогда «вход по почте» становится входом по желанию.
3. **Домен проверяется РАНЬШЕ, чем существование учётной записи.** Иначе по
   разным ответам («нет такого» против «домен не разрешён») можно было бы
   перебирать сотрудников заказчика.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/test_sso_rules.py -v``.
"""

from __future__ import annotations

import pytest

from app.domains.sso.rules import (
    DOMAIN_NOT_ALLOWED,
    EMAIL_UNVERIFIED,
    INCOMPLETE,
    JIT_DISABLED,
    NOT_CONFIGURED,
    PROVIDER_OIDC,
    REFUSAL_TITLES,
    SECRET_MISSING,
    USER_INACTIVE,
    SsoConfig,
    SsoRefused,
    decide_jit,
    ensure_usable,
    normalize_domains,
)


def _config(**overrides) -> SsoConfig:
    base = {
        "provider": PROVIDER_OIDC,
        "issuer": "https://login.acme.ru",
        "client_id": "ptd",
        "client_secret_env": "ACME_SSO_SECRET",
        "authorization_endpoint": "https://login.acme.ru/authorize",
        "token_endpoint": "https://login.acme.ru/token",
        "jwks_uri": "https://login.acme.ru/jwks",
        "email_domains": ("acme.ru",),
        "jit_enabled": False,
        "default_role": "worker",
    }
    base.update(overrides)
    return SsoConfig(**base)


class TestМожноЛиНачинать:
    def test_не_настроено_называется_словами(self) -> None:
        with pytest.raises(SsoRefused) as exc:
            ensure_usable(None, secret="s")
        assert exc.value.reason == NOT_CONFIGURED
        assert "не настроен" in exc.value.title

    def test_выключенный_провайдер_это_не_настроено(self) -> None:
        with pytest.raises(SsoRefused) as exc:
            ensure_usable(SsoConfig(), secret="s")
        assert exc.value.reason == NOT_CONFIGURED

    def test_недозаполненная_настройка_звучит_иначе(self) -> None:
        """«Не настроено» и «настроено наполовину» чинят разные люди: первое —
        администратор заказчика, второе — он же, но зная, чего не хватает."""

        with pytest.raises(SsoRefused) as exc:
            ensure_usable(_config(jwks_uri=""), secret="s")
        assert exc.value.reason == INCOMPLETE

    def test_пустой_список_доменов_это_незаполненная_настройка(self) -> None:
        """ГЛАВНОЕ РЕШЕНИЕ: пусто — это запрет, а не разрешение всем."""

        with pytest.raises(SsoRefused) as exc:
            ensure_usable(_config(email_domains=()), secret="s")
        assert exc.value.reason == INCOMPLETE

    def test_нет_секрета_в_окружении_это_отдельная_причина(self) -> None:
        """Настройка есть, а секрета нет — ошибка РАЗВЁРТЫВАНИЯ. Смешать её с
        «не настроено» значит отправить администратора чинить не то."""

        with pytest.raises(SsoRefused) as exc:
            ensure_usable(_config(), secret=None)
        assert exc.value.reason == SECRET_MISSING

    def test_полная_настройка_проходит(self) -> None:
        assert ensure_usable(_config(), secret="s").client_id == "ptd"

    def test_у_каждой_причины_есть_подпись_словами(self) -> None:
        for code, title in REFUSAL_TITLES.items():
            assert title.strip() and title != code


class TestКогоПускаем:
    def test_известного_сотрудника_пускаем_без_заведения(self) -> None:
        decision = decide_jit(
            _config(), email="ivan@acme.ru", email_verified=True, existing_user_active=True
        )
        assert decision.create is False
        assert decision.email == "ivan@acme.ru"

    def test_неподтверждённый_адрес_не_принимается(self) -> None:
        """В чужом каталоге адрес мог вписать сам пользователь."""

        with pytest.raises(SsoRefused) as exc:
            decide_jit(
                _config(), email="ivan@acme.ru", email_verified=False, existing_user_active=True
            )
        assert exc.value.reason == EMAIL_UNVERIFIED

    def test_чужой_домен_не_проходит(self) -> None:
        with pytest.raises(SsoRefused) as exc:
            decide_jit(
                _config(), email="ivan@other.ru", email_verified=True, existing_user_active=None
            )
        assert exc.value.reason == DOMAIN_NOT_ALLOWED

    def test_домен_проверяется_раньше_существования(self) -> None:
        """ГЛАВНАЯ ТОНКОСТЬ. Иначе по разным ответам можно было бы перебирать
        сотрудников заказчика: «нет такого» и «домен не разрешён» — разные
        ответы на один и тот же подбор адреса."""

        with pytest.raises(SsoRefused) as exc:
            decide_jit(
                _config(jit_enabled=True),
                email="ivan@other.ru",
                email_verified=True,
                existing_user_active=None,
            )
        assert exc.value.reason == DOMAIN_NOT_ALLOWED

    def test_пустой_список_доменов_не_пускает_никого(self) -> None:
        """ВТОРАЯ ЛИНИЯ ОБОРОНЫ, и она проверяется отдельно.

        Первая — ``ensure_usable``: она не даёт начать вход с незаполненными
        доменами. Но правило «пусто значит запрет» должно держаться и здесь:
        мутация «пустой список разрешает всем» НЕ покраснела, пока этой проверки
        не было, — значит, вторая линия была украшением, а не обороной.
        """

        with pytest.raises(SsoRefused) as exc:
            decide_jit(
                _config(email_domains=(), jit_enabled=True),
                email="kto_ugodno@other.ru",
                email_verified=True,
                existing_user_active=None,
            )
        assert exc.value.reason == DOMAIN_NOT_ALLOWED

    def test_нового_заводим_только_если_разрешено(self) -> None:
        with pytest.raises(SsoRefused) as exc:
            decide_jit(
                _config(), email="new@acme.ru", email_verified=True, existing_user_active=None
            )
        assert exc.value.reason == JIT_DISABLED

        decision = decide_jit(
            _config(jit_enabled=True, default_role="ot_specialist"),
            email="new@acme.ru",
            email_verified=True,
            existing_user_active=None,
        )
        assert decision.create is True
        assert decision.role == "ot_specialist"

    def test_отключённая_учётка_не_оживает_через_sso(self) -> None:
        """Иначе увольнение, оформленное отключением, отменялось бы входом."""

        with pytest.raises(SsoRefused) as exc:
            decide_jit(
                _config(jit_enabled=True),
                email="ivan@acme.ru",
                email_verified=True,
                existing_user_active=False,
            )
        assert exc.value.reason == USER_INACTIVE

    def test_адрес_приводится_к_одному_виду(self) -> None:
        decision = decide_jit(
            _config(), email="  IVAN@Acme.RU ", email_verified=True, existing_user_active=True
        )
        assert decision.email == "ivan@acme.ru"

    def test_пустой_адрес_отвергается(self) -> None:
        with pytest.raises(SsoRefused) as exc:
            decide_jit(_config(), email=None, email_verified=True, existing_user_active=None)
        assert exc.value.reason == EMAIL_UNVERIFIED


class TestДомены:
    def test_приводятся_к_одному_виду(self) -> None:
        assert normalize_domains([" @Acme.RU ", "acme.ru", "sub.acme.ru"]) == (
            "acme.ru",
            "sub.acme.ru",
        )

    def test_мусор_не_ломает_разбор(self) -> None:
        assert normalize_domains(None) == ()
        assert normalize_domains("acme.ru") == ()
