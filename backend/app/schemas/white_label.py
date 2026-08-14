"""Схемы бренда приложения (BIZ-52 срез-4, Доп. №1 разд. 52.2)."""

from __future__ import annotations

import re

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema

#: Управляющие символы и лишние пробелы в полях, которые уезжают в заголовки
#: письма. Держим правило рядом со схемой — это её инвариант, а не деталь почты.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
_SPACES = re.compile(r"\s+")

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
    #: Признаки, а не сами байты: картинки забираются отдельными ручками
    #: (`/public/branding/logo|favicon`), чтобы JSON бренда оставался лёгким,
    #: а браузер мог кэшировать картинку по ETag.
    has_logo: bool = False
    has_favicon: bool = False


class TenantBrandingPatch(BaseSchema):
    """Своя настройка. Пустое поле = «не задано», наследование возвращается."""

    app_name: str | None = Field(default=None, max_length=120)
    primary_color: str | None = Field(default=None, pattern=_HSL_TRIPLET)
    support_email: str | None = Field(default=None, max_length=255)

    @field_validator("app_name", "support_email", mode="before")
    @classmethod
    def _no_control_characters(cls, value: object) -> object:
        """Вычистить переводы строк и прочие управляющие символы.

        BIZ-52 срез-10: эти поля уезжают в ЗАГОЛОВКИ письма, а перевод строки в
        заголовке — это конец заголовка и начало следующего. Python такую строку
        отвергает исключением, поэтому имя, скопированное из документа вместе с
        переносом, лишило бы писем всех клиентов партнёра, и причина никак не
        связалась бы с настройкой бренда.

        Чистим, а не отказываем: перенос в названии приложения смысла не несёт,
        а экран бренда перечитывает сохранённое, так что человек сразу видит
        результат. Почта чистит ещё раз — строки, сохранённые до этой правки,
        уже лежат в базе.
        """

        if not isinstance(value, str):
            return value
        return _SPACES.sub(" ", _CONTROL.sub(" ", value)).strip() or None


class TenantBrandingRead(TenantBrandingPatch):
    """Своя настройка плюс то, что из неё получилось после наследования.

    Оба поля вместе, потому что по одной своей настройке нельзя понять, что
    увидит пользователь: незаполненные поля берутся выше по цепочке.
    """

    #: Свои картинки (не унаследованные): партнёру нужно видеть, загрузил ли
    #: он логотип сам, — «есть действующий» об этом не говорит.
    has_logo: bool = False
    has_favicon: bool = False
    effective: AppBrandRead
