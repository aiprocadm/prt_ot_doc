"""Настройка единого входа у арендатора (BIZ-53 разд. 53.3, срез-204).

СЕКРЕТА ПРИЛОЖЕНИЯ ЗДЕСЬ НЕТ И НЕ БУДЕТ. В строке лежит только ИМЯ переменной
окружения (``client_secret_env``), из которой секрет читается на месте. Секрет
в таблице пережил бы её резервную копию, выгрузку для отладки и любой запрос
«покажите строку»; имя переменной — не пережило бы ничего, потому что само по
себе бесполезно.

Таблица арендаторская: у каждого заказчика свой провайдер входа. Значит, RLS
(SEC-65) обязателен — в строке адреса корпоративного каталога и список
разрешённых почтовых доменов, то есть карта того, кто и откуда входит.
"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.domains.sso.rules import PROVIDER_DISABLED
from app.models.base import TenantBaseModel

__all__ = ["TenantSsoConfig"]


class TenantSsoConfig(TenantBaseModel):
    """Одна настройка на арендатора."""

    __tablename__ = "tenant_sso_config"

    #: ``disabled`` (умолчание) или ``oidc``. Умолчание — прежнее поведение:
    #: существующие развёртывания не замечают появления этой таблицы.
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default=PROVIDER_DISABLED)

    issuer: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    client_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    #: ИМЯ переменной окружения, а не секрет. См. заголовок модуля.
    client_secret_env: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    authorization_endpoint: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    token_endpoint: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    jwks_uri: Mapped[str] = mapped_column(String(512), nullable=False, default="")

    #: Разрешённые почтовые домены. Пустой список — запрет всем, а не «можно
    #: всем»: правило записано в ``app.domains.sso.rules`` и объяснено там.
    email_domains: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    #: Заводить ли сотрудника при первом входе.
    jit_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_role: Mapped[str] = mapped_column(String(64), nullable=False, default="worker")

    __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_sso_config_tenant"),)
