"""SEC-68, разд. 68.2: защита публичных форм от ботов — как НАСТРОЙКА.

ТЗ требует буквально: «CAPTCHA/anti-bot на публичных формах регистрации/загрузки
данных». В продукте публичная форма одна — самостоятельная регистрация
арендатора (`/public/signup`), и каждый успешный запрос к ней создаёт СХЕМУ В
БАЗЕ. Это самая дорогая кнопка, какая вообще выставлена в интернет.

ЧТО БЫЛО. Форма прикрыта тремя мерами: выключена по умолчанию, свой строгий
счётчик попыток по адресу (три в час) и стартовая редакция вместо «всё
включено». Проверки «человек ли это» не было вообще: лимит по адресу не мешает
боту с сотней адресов, а именно так регистрационный спам и делают.

ПОЧЕМУ НАСТРОЙКА, А НЕ КОД. Любая капча — это внешняя служба с ключом. В этом
продукте действует записанное правило: **подключение внешней зависимости —
настройка, а не разработка**, и ненастроенное честно говорит, что оно не
настроено. Поэтому здесь шов: платформа умеет спрашивать у службы «человек ли
это», а какую службу подключить и подключать ли вообще — решает владелец.

ЧЕСТНО О ПОВЕДЕНИИ БЕЗ НАСТРОЙКИ. Регистрация НЕ ломается: она продолжает
работать на прежних мерах. Но это решение названо вслух, а не умолчано: при
включении публичной регистрации без анти-бота в журнал уходит предупреждение —
владелец должен знать, что самая дорогая кнопка продукта открыта в интернет без
проверки «человек ли это».

СЕКРЕТ НЕ ХРАНИТСЯ В НАСТРОЙКАХ. В конфигурации лежит ИМЯ переменной окружения
(приём среза-204): секрет в базе или в файле настроек пережил бы их резервную
копию и любую выгрузку.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

__all__ = [
    "PROVIDER_URLS",
    "AntiBotConfig",
    "AntiBotRefusal",
    "resolve_config",
    "verify_human",
]


class AntiBotRefusal(Exception):
    """Проверка «человек ли это» не пройдена.

    Причина внутри — для журнала, наружу отдаётся одинаковый ответ: разные
    ответы («нет токена» / «токен не принят») подсказывали бы боту, где он
    ошибся.
    """


#: Адреса проверки у поддерживаемых служб. Оба принимают одинаковое тело
#: (``secret`` + ``response``) и отвечают полем ``success`` — поэтому вторая
#: служба не стоит ни строчки отдельного кода.
PROVIDER_URLS: dict[str, str] = {
    "turnstile": "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    "recaptcha": "https://www.google.com/recaptcha/api/siteverify",
}


@dataclass(frozen=True)
class AntiBotConfig:
    """Разрешённая настройка: какая служба и какой у неё секрет."""

    provider: str
    secret: str

    @property
    def url(self) -> str:
        return PROVIDER_URLS[self.provider]


def resolve_config(settings: object) -> AntiBotConfig | None:
    """Настройка анти-бота или ``None``, если её нет.

    ``None`` — это НЕ ошибка: так выглядит «владелец не подключал». Ошибкой
    считается настройка неполная (служба названа, а секрета нет) — тогда
    молчаливый пропуск был бы худшим исходом: владелец думает, что защита
    включена, а её нет.
    """

    provider = str(getattr(settings, "signup_antibot_provider", "") or "").strip().lower()
    if not provider:
        return None
    if provider not in PROVIDER_URLS:
        raise AntiBotRefusal(f"неизвестная служба проверки: {provider!r}")

    secret_env = str(getattr(settings, "signup_antibot_secret_env", "") or "").strip()
    secret = os.environ.get(secret_env, "").strip() if secret_env else ""
    if not secret:
        raise AntiBotRefusal(
            f"служба {provider!r} названа, но секрет в переменной {secret_env!r} пуст — "
            "защита от ботов НЕ работает, хотя выглядит включённой"
        )
    return AntiBotConfig(provider=provider, secret=secret)


async def verify_human(
    config: AntiBotConfig,
    token: str | None,
    *,
    remote_ip: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Спросить у службы, человек ли отправил форму.

    Клиент передаётся снаружи (приём среза-204): так проверку можно прогнать в
    тестах, не выходя в сеть, и это не «мок ради мока» — это тот же шов, что у
    единого входа.

    Адрес службы ЗАКРЫТЫЙ (см. ``PROVIDER_URLS``): его не задаёт ни арендатор,
    ни пользователь, поэтому подмена адреса здесь невозможна и проверка SSRF не
    нужна — в отличие от вебхуков, где адрес задаёт заказчик (разд. 64.3).
    """

    if not token:
        raise AntiBotRefusal("форма отправлена без ответа на проверку")

    payload = {"secret": config.secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        response = await client.post(config.url, data=payload)
        response.raise_for_status()
        body = response.json()
    except Exception as exc:  # noqa: BLE001 - наружу уходит один и тот же отказ
        # Служба недоступна — это ОТКАЗ, а не пропуск. Пропускать «пока служба
        # лежит» значит иметь защиту ровно до того момента, когда она нужна.
        raise AntiBotRefusal(f"служба проверки недоступна: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()

    if not bool(body.get("success")):
        raise AntiBotRefusal(f"служба не подтвердила человека: {body.get('error-codes')}")


def warn_if_unprotected(settings: object) -> None:
    """Сказать вслух, что самая дорогая кнопка открыта без проверки.

    Вызывается при включённой публичной регистрации. Это не шум: включить
    регистрацию и не заметить, что анти-бота нет, — ровно тот случай, когда
    молчание читается как «всё в порядке».
    """

    if not getattr(settings, "self_service_signup_enabled", False):
        return
    if str(getattr(settings, "signup_antibot_provider", "") or "").strip():
        return
    logger.warning(
        "public_signup.antibot_not_configured",
        extra={
            "hint": (
                "публичная регистрация включена без проверки «человек ли это»: "
                "бот с набором адресов обойдёт лимит по адресу. Настройте "
                "SIGNUP_ANTIBOT_PROVIDER + SIGNUP_ANTIBOT_SECRET_ENV"
            )
        },
    )
