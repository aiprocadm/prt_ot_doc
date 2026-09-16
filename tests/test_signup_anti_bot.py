"""SEC-68, разд. 68.2: «человек ли это» на публичной форме регистрации.

ТЗ требует «CAPTCHA/anti-bot на публичных формах регистрации/загрузки данных».
Публичная форма в продукте одна — самостоятельная регистрация арендатора, и
каждый её успешный запрос создаёт СХЕМУ В БАЗЕ. Это самая дорогая кнопка,
выставленная в интернет.

До среза-213 форму прикрывали три меры: выключена по умолчанию, свой строгий
счётчик попыток по адресу и стартовая редакция. Проверки «человек ли это» не
было вовсе — а лимит по адресу не мешает боту с сотней адресов, именно так
регистрационный спам и делают.

Здесь закрепляются РЕШЕНИЯ, а не вёрстка:

1. служба подключается настройкой; не подключена — регистрация работает, но
   об этом пишется предупреждение (молчание читалось бы как «защита есть»);
2. **неполная настройка хуже отсутствия** — служба названа, секрета нет:
   владелец уверен, что защищён, а защиты нет. Такой случай = отказ;
3. **служба недоступна = отказ, а не пропуск**: пропускать «пока служба лежит»
   значит иметь защиту ровно до того момента, когда она нужна;
4. ответ ОДИНАКОВ для «нет ответа» и «ответ не принят» — разные ответы
   подсказывали бы боту, где он ошибся;
5. секрет берётся из переменной окружения по ИМЕНИ, а не лежит в настройках.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.core.anti_bot import (
    PROVIDER_URLS,
    AntiBotRefusal,
    resolve_config,
    verify_human,
)


def _settings(**overrides) -> SimpleNamespace:
    base = {
        "self_service_signup_enabled": True,
        "signup_antibot_provider": "",
        "signup_antibot_secret_env": "TEST_ANTIBOT_SECRET",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_без_настройки_проверки_нет() -> None:
    """Не подключено — не значит сломано: регистрация работает как раньше."""

    assert resolve_config(_settings()) is None


def test_неполная_настройка_отвергается(monkeypatch: pytest.MonkeyPatch) -> None:
    """ХУЖЕ, ЧЕМ НИЧЕГО: служба названа, секрета нет — владелец уверен зря."""

    monkeypatch.delenv("TEST_ANTIBOT_SECRET", raising=False)
    with pytest.raises(AntiBotRefusal):
        resolve_config(_settings(signup_antibot_provider="turnstile"))


def test_неизвестная_служба_отвергается() -> None:
    with pytest.raises(AntiBotRefusal):
        resolve_config(_settings(signup_antibot_provider="волшебная-капча"))


def test_секрет_берётся_из_окружения_по_имени(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_ANTIBOT_SECRET", "s3cret")
    config = resolve_config(_settings(signup_antibot_provider="turnstile"))

    assert config is not None
    assert config.secret == "s3cret"
    assert config.url == PROVIDER_URLS["turnstile"]


@pytest.mark.anyio
async def test_подтверждённый_человек_проходит(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_ANTIBOT_SECRET", "s3cret")
    config = resolve_config(_settings(signup_antibot_provider="turnstile"))
    assert config is not None

    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json={"success": True})

    async with _client(handler) as client:
        await verify_human(config, "ответ-от-браузера", remote_ip="203.0.113.7", client=client)

    # Секрет и ответ уходят службе; адрес — чтобы она видела источник.
    assert seen["secret"] == "s3cret"
    assert seen["response"] == "ответ-от-браузера"
    assert seen["remoteip"] == "203.0.113.7"


@pytest.mark.anyio
async def test_пустой_ответ_не_проходит(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_ANTIBOT_SECRET", "s3cret")
    config = resolve_config(_settings(signup_antibot_provider="turnstile"))
    assert config is not None

    with pytest.raises(AntiBotRefusal):
        await verify_human(config, None)


@pytest.mark.anyio
async def test_служба_не_подтвердила_человека(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_ANTIBOT_SECRET", "s3cret")
    config = resolve_config(_settings(signup_antibot_provider="turnstile"))
    assert config is not None

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": False, "error-codes": ["invalid-input"]})

    async with _client(handler) as client:
        with pytest.raises(AntiBotRefusal):
            await verify_human(config, "подделка", client=client)


@pytest.mark.anyio
async def test_недоступная_служба_это_отказ_а_не_пропуск(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ГЛАВНОЕ. Защита, которая отключается вместе со службой, — не защита."""

    monkeypatch.setenv("TEST_ANTIBOT_SECRET", "s3cret")
    config = resolve_config(_settings(signup_antibot_provider="turnstile"))
    assert config is not None

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    async with _client(handler) as client:
        with pytest.raises(AntiBotRefusal):
            await verify_human(config, "ответ", client=client)


def test_адрес_службы_закрытый_список() -> None:
    """Адрес не задаётся ни арендатором, ни пользователем — подменить нечего.

    Это отличие от вебхуков (разд. 64.3), где адрес задаёт заказчик и потому
    нужна проверка на внутренние диапазоны.
    """

    assert set(PROVIDER_URLS) == {"turnstile", "recaptcha"}
    assert all(url.startswith("https://") for url in PROVIDER_URLS.values())
