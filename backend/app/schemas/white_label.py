"""Схемы бренда приложения (BIZ-52 срез-4, Доп. №1 разд. 52.2)."""

from __future__ import annotations

from pydantic import Field

from app.schemas.base import BaseSchema

#: Цвет хранится и отдаётся HSL-триплетом Tailwind (`H S% L%`) — ровно в том
#: виде, в каком его ждёт CSS-переменная `--primary`. Перевод формата на каждой
#: отрисовке однажды разошёлся бы с интерфейсом, и выглядело бы это как «тема не
#: применилась».
_HSL_TRIPLET = r"^\d{1,3}(\.\d+)?\s+\d{1,3}(\.\d+)?%\s+\d{1,3}(\.\d+)?%$"


class AppBrandRead(BaseSchema):
    """Действующий бренд — то, что показывать пользователю."""

    app_name: str
    primary_color: str
    support_email: str | None = None
    #: Откуда бренд: `self` / `reseller` / `platform`. Интерфейсу это нужно,
    #: чтобы честно сказать партнёру «сейчас у вас бренд платформы», а не
    #: оставлять его гадать, применилась настройка или нет.
    source: str


class TenantBrandingPatch(BaseSchema):
    """Своя настройка. Пустое поле = «не задано», наследование возвращается."""

    app_name: str | None = Field(default=None, max_length=120)
    primary_color: str | None = Field(default=None, pattern=_HSL_TRIPLET)
    support_email: str | None = Field(default=None, max_length=255)


class TenantBrandingRead(TenantBrandingPatch):
    """Своя настройка плюс то, что из неё получилось после наследования.

    Оба поля вместе, потому что по одной своей настройке нельзя понять, что
    увидит пользователь: незаполненные поля берутся выше по цепочке.
    """

    effective: AppBrandRead
