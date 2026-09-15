"""Единый вход (SSO) — чистые правила (BIZ-53 разд. 53.3, срез-204).

ЗАЧЕМ. Разд. 53.3 требует для enterprise-аренды «SSO/SAML/LDAP». Дорожная
карта держала это отдельной задачей (P10-13) со статусом «не начато»: сотрудник
крупного заказчика заводил в платформе ЕЩЁ ОДИН пароль, а служба безопасности
заказчика не могла ни отозвать доступ централизованно, ни потребовать своей
двухфакторности.

ПРИНЦИП ТОТ ЖЕ, ЧТО У ОСТАЛЬНЫХ ВНЕШНИХ ЗАВИСИМОСТЕЙ (срезы 182–193): внешнего
поставщика личности нельзя купить кодом, но можно сделать его подключение
НАСТРОЙКОЙ, а не разработкой. Здесь заведён шов: провайдер объявляется у
арендатора, ненастроенный вход ЧЕСТНО ОТКАЗЫВАЕТ и называет причину словами.

ПОЧЕМУ OIDC, А НЕ SAML. ТЗ называет оба. OpenID Connect выбран первым, потому
что он проверяется тем же, что у платформы уже есть (подписанный токен, JWKS,
HTTPS), и не требует новой зависимости — а SAML потребовал бы библиотеку
разбора и подписи XML, то есть новую поверхность атаки ради формата, который
корпоративные провайдеры и так отдают через OIDC. SAML остаётся отдельной
работой, и это сказано честно, а не выдано за сделанное.

ПОЧЕМУ СЕКРЕТ КЛИЕНТА НЕ ЛЕЖИТ В БАЗЕ. В настройке записано только ИМЯ
переменной окружения (``client_secret_env``), а сам секрет живёт там, где живут
секреты развёртывания — в окружении, куда его кладёт Vault, KMS или скрипт
установки. Секрет в таблице пережил бы её резервную копию, выгрузку для отладки
и любой запрос «покажите строку». Это то же решение, что в SEC-67: хранилище
подключается настройкой, а код знает только адрес.

ЗАПУСК проверок: ``PYTHONPATH=backend pytest tests/test_sso_rules.py -v``.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "JIT_DISABLED",
    "JitDecision",
    "NOT_CONFIGURED",
    "PROVIDER_DISABLED",
    "PROVIDER_OIDC",
    "REFUSAL_TITLES",
    "SsoConfig",
    "SsoRefused",
    "decide_jit",
    "ensure_usable",
    "normalize_domains",
]

PROVIDER_DISABLED = "disabled"
PROVIDER_OIDC = "oidc"

#: Причины отказа. Код — для ветвления, подпись — для человека: «вход не
#: настроен» и «ваш домен не разрешён» человек должен различать сам, иначе он
#: будет писать в поддержку платформы там, где решение у его же администратора.
NOT_CONFIGURED = "not_configured"
INCOMPLETE = "incomplete"
SECRET_MISSING = "secret_missing"
JIT_DISABLED = "jit_disabled"
DOMAIN_NOT_ALLOWED = "domain_not_allowed"
EMAIL_UNVERIFIED = "email_unverified"
USER_INACTIVE = "user_inactive"

REFUSAL_TITLES: dict[str, str] = {
    NOT_CONFIGURED: "Единый вход для этой организации не настроен",
    INCOMPLETE: "Настройка единого входа заполнена не полностью — обратитесь к администратору",
    SECRET_MISSING: "Секрет приложения не выдан окружению — вход временно невозможен",
    JIT_DISABLED: "Вход разрешён только сотрудникам, заведённым в системе заранее",
    DOMAIN_NOT_ALLOWED: "Этот почтовый домен не разрешён для входа через SSO",
    EMAIL_UNVERIFIED: "Поставщик входа не подтвердил адрес почты",
    USER_INACTIVE: "Учётная запись отключена",
}


class SsoRefused(PermissionError):
    """Отказ с ПРИЧИНОЙ. Молчаливый отказ читается как поломка платформы."""

    def __init__(self, reason: str) -> None:
        super().__init__(REFUSAL_TITLES[reason])
        self.reason = reason
        self.title = REFUSAL_TITLES[reason]


@dataclass(frozen=True, slots=True)
class SsoConfig:
    """Настройка единого входа у арендатора.

    ``client_secret_env`` — ИМЯ переменной окружения, а не сам секрет: см.
    заголовок модуля.
    """

    provider: str = PROVIDER_DISABLED
    issuer: str = ""
    client_id: str = ""
    client_secret_env: str = ""
    authorization_endpoint: str = ""
    token_endpoint: str = ""
    jwks_uri: str = ""
    #: Разрешённые почтовые домены. ПУСТОЙ СПИСОК — запрет всем, а не «можно
    #: всем»: «пустое значит всё» выглядит удобно ровно до первой забытой
    #: настройки, после которой в контур заказчика входит кто угодно с любой
    #: почтой, которую подпишет его провайдер.
    email_domains: tuple[str, ...] = ()
    #: Заводить ли сотрудника при первом входе (JIT). Выключено — вход только
    #: тем, кто заведён заранее.
    jit_enabled: bool = False
    #: Роль, с которой заводится сотрудник при JIT.
    default_role: str = "worker"


def normalize_domains(raw: object) -> tuple[str, ...]:
    """Домены к одному виду: без пробелов, в нижнем регистре, без «@»."""

    if not isinstance(raw, (list, tuple)):
        return ()
    out: list[str] = []
    for item in raw:
        value = str(item).strip().lower().lstrip("@")
        if value and value not in out:
            out.append(value)
    return tuple(out)


def ensure_usable(config: SsoConfig | None, *, secret: str | None) -> SsoConfig:
    """Можно ли вообще начинать вход. Отказ называет причину.

    Проверка стоит ДО обращения к провайдеру: увести человека на чужой сайт и
    вернуть его с ошибкой — худший способ сказать «у вас не настроено».
    """

    if config is None or config.provider == PROVIDER_DISABLED:
        raise SsoRefused(NOT_CONFIGURED)
    required = (
        config.issuer,
        config.client_id,
        config.client_secret_env,
        config.authorization_endpoint,
        config.token_endpoint,
        config.jwks_uri,
    )
    if not all(value.strip() for value in required) or not config.email_domains:
        raise SsoRefused(INCOMPLETE)
    if not secret:
        # Настройка есть, а секрета в окружении нет: это ошибка развёртывания, и
        # она обязана звучать иначе, чем «не настроено», — чинить их разным людям.
        raise SsoRefused(SECRET_MISSING)
    return config


@dataclass(frozen=True, slots=True)
class JitDecision:
    """Что делать с человеком, пришедшим от провайдера."""

    email: str
    create: bool
    role: str


def decide_jit(
    config: SsoConfig,
    *,
    email: str | None,
    email_verified: bool,
    existing_user_active: bool | None,
) -> JitDecision:
    """Пускать ли и заводить ли сотрудника.

    ``existing_user_active`` — ``None``, если такого человека в контуре нет.

    ПОРЯДОК ПРОВЕРОК ВАЖЕН. Домен проверяется РАНЬШЕ, чем существование
    учётной записи: иначе по разным ответам («нет такого» против «домен не
    разрешён») можно было бы перебирать сотрудников заказчика.
    """

    address = (email or "").strip().lower()
    if not address or "@" not in address:
        raise SsoRefused(EMAIL_UNVERIFIED)
    if not email_verified:
        # Неподтверждённый адрес принимать нельзя: в чужом каталоге его мог
        # вписать сам пользователь, и тогда «вход по почте» становится входом
        # по желанию.
        raise SsoRefused(EMAIL_UNVERIFIED)
    domain = address.rsplit("@", 1)[1]
    if domain not in config.email_domains:
        raise SsoRefused(DOMAIN_NOT_ALLOWED)
    if existing_user_active is False:
        raise SsoRefused(USER_INACTIVE)
    if existing_user_active is None:
        if not config.jit_enabled:
            raise SsoRefused(JIT_DISABLED)
        return JitDecision(email=address, create=True, role=config.default_role)
    return JitDecision(email=address, create=False, role="")
