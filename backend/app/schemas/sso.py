"""Схемы единого входа (BIZ-53 разд. 53.3, срез-204).

СЕКРЕТ ПРИЛОЖЕНИЯ ЗДЕСЬ НЕ ХОДИТ НИ В ОДНУ СТОРОНУ. Наружу отдаётся только имя
переменной окружения и признак «выдан ли он окружению» — этого хватает, чтобы
администратор понял, чинить ему настройку или развёртывание, и не хватает,
чтобы секрет утёк в журнал запросов или в снимок экрана.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.domains.enterprise.decisions import DECLINED, decision_for
from app.domains.sso.rules import PROVIDER_DISABLED, PROVIDER_OIDC

__all__ = ["SsoConfigRead", "SsoConfigWrite", "SsoStartResponse", "SsoStatusResponse"]


class SsoStatusResponse(BaseModel):
    """Показывать ли кнопку «Войти через SSO» на экране входа."""

    enabled: bool = False


class SsoStartResponse(BaseModel):
    authorization_url: str


class SsoConfigWrite(BaseModel):
    """Заявка на настройку. Пустой список доменов при включённом провайдере
    отвергается: «пусто значит всем» — самая дорогая из удобных умолчаний."""

    provider: Literal[PROVIDER_DISABLED, PROVIDER_OIDC] = PROVIDER_DISABLED
    issuer: str = Field(default="", max_length=512)
    client_id: str = Field(default="", max_length=255)
    #: ИМЯ переменной окружения, а не секрет.
    client_secret_env: str = Field(default="", max_length=128)
    authorization_endpoint: str = Field(default="", max_length=512)
    token_endpoint: str = Field(default="", max_length=512)
    jwks_uri: str = Field(default="", max_length=512)
    email_domains: list[str] = Field(default_factory=list)
    jit_enabled: bool = False
    default_role: str = Field(default="worker", max_length=64)

    model_config = {"extra": "forbid"}

    @model_validator(mode="before")
    @classmethod
    def _explain_declined_protocols(cls, data):
        """Назвать РЕШЕНИЕ, а не отвертеться «недопустимым значением».

        ТЗ разд. 53.3 обещает крупному заказчику «SSO/SAML/LDAP». Его
        администратор, увидев ответ «должно быть disabled или oidc», решит, что
        у платформы недоделка или сломался список, — и пойдёт в поддержку. На
        деле это осознанное решение с обходным путём, и сказать об этом обязана
        сама платформа: причина и что делать берутся из реестра решений
        (``domains/enterprise/decisions``), чтобы ответ не разошёлся с ним.
        """

        if not isinstance(data, dict):
            return data
        asked = str(data.get("provider") or "").strip().lower()
        decision = decision_for(asked)
        if decision is not None and decision.state == DECLINED:
            raise ValueError(
                f"{decision.requirement} — не поддерживается осознанно. "
                f"Причина: {decision.reason}. Что делать: {decision.workaround}."
            )
        return data

    @model_validator(mode="after")
    def _check(self) -> SsoConfigWrite:
        if self.provider == PROVIDER_DISABLED:
            return self
        missing = [
            name
            for name, value in (
                ("issuer", self.issuer),
                ("client_id", self.client_id),
                ("client_secret_env", self.client_secret_env),
                ("authorization_endpoint", self.authorization_endpoint),
                ("token_endpoint", self.token_endpoint),
                ("jwks_uri", self.jwks_uri),
            )
            if not value.strip()
        ]
        if missing:
            raise ValueError("не заполнено: " + ", ".join(missing))
        if not [d for d in self.email_domains if str(d).strip()]:
            raise ValueError("укажите хотя бы один разрешённый почтовый домен")
        for url in (self.authorization_endpoint, self.token_endpoint, self.jwks_uri):
            # Обмен секретом и проверка ключей по HTTP означали бы, что любой на
            # пути подменит и то и другое. Это не придирка к схеме, а условие,
            # без которого весь единый вход не имеет смысла.
            if not url.strip().lower().startswith("https://"):
                raise ValueError("адреса провайдера должны начинаться с https://")
        return self


class SsoConfigRead(SsoConfigWrite):
    """То же плюс признак «секрет выдан окружению». Самого секрета нет."""

    secret_present: bool = False

    @model_validator(mode="after")
    def _check(self) -> SsoConfigRead:  # type: ignore[override]
        # Чтение НЕ проверяет полноту: отдать наполовину заполненную настройку
        # администратору надо именно затем, чтобы он увидел, чего не хватает.
        return self
