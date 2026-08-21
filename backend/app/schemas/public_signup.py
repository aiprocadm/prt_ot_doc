"""Схемы самостоятельной регистрации (BIZ-53 срез-3, Доп. №1 разд. 53.2)."""

from __future__ import annotations

from pydantic import EmailStr, Field

from app.schemas.base import BaseSchema

__all__ = ["SignupRequest", "SignupResult"]


class SignupRequest(BaseSchema):
    """Заявка на самостоятельный старт.

    Полей ровно столько, сколько нужно, чтобы войти: ТЗ обещает старт «без
    долгой настройки», и каждое лишнее поле здесь — причина не дойти до конца.
    Отрасль необязательна: она выбирает отраслевой стартовый набор, а без неё
    выдаётся общий.
    """

    #: Адрес арендатора и имя схемы в базе. Проверяется по закрытому набору
    #: символов в самой ручке — иначе сломался бы либо адрес, либо SQL.
    slug: str = Field(min_length=3, max_length=40)
    company_name: str = Field(min_length=1, max_length=255)
    owner_email: EmailStr
    #: Пароль задаёт сам регистрирующийся; в ответе он НЕ повторяется — эхо
    #: попало бы в журналы прокси и историю браузера.
    owner_password: str = Field(min_length=8, max_length=128)
    industry: str | None = Field(default=None, max_length=64)


class SignupResult(BaseSchema):
    """Чем войти и что получено."""

    tenant_slug: str
    owner_email: str
    #: Стартовая редакция (разд. 53.1): полный набор продаётся, а не раздаётся.
    plan_code: str
    #: Предупреждения выдачи — например, «отраслевого набора нет». Их прячут
    #: только там, где не хотят объяснять, почему система выглядит пустой.
    warnings: list[str] = Field(default_factory=list)
