"""Как бренд партнёра выглядит в письме (BIZ-52 срез-10, Доп. №1 разд. 52.2).

Разд. 52.2 требует «скрытия любых упоминаний исходного вендора». Приложение это
уже делает: имя, цвет, логотип и юридические тексты подменяются брендом
партнёра. Письма — нет: они уходили с адреса платформы, без отображаемого имени
и без подписи, поэтому клиент партнёра узнавал вендора из первого же
уведомления.

Правила здесь чистые (без базы и без SMTP) намеренно: подстановка чужого текста
в заголовок письма — место, где ошибка не «некрасиво выглядит», а рвёт доставку
или подделывает письмо, и проверять её надо построчно.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domains.reseller.white_label import AppBrand

#: Управляющие символы, которые нельзя пускать в заголовок.
#:
#: Перевод строки в заголовке — это конец заголовка и начало следующего, то есть
#: способ дописать в письмо чужой `Bcc`. Python такую строку отвергает
#: исключением, и это ХУЖЕ, чем кажется: имя бренда задаёт партнёр, схема
#: переводы строк пропускает (там только ограничение длины), поэтому имя,
#: скопированное из документа вместе с переносом, ронял бы отправку ВСЕХ писем
#: его клиентам. Поэтому чистим, а не надеемся.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
_SPACES = re.compile(r"\s+")

#: Простейшая проверка адреса. Не заменяет валидацию — нужна ровно для того,
#: чтобы мусор из настройки не уехал в заголовок `Reply-To`.
_ADDRESS = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class MailIdentity:
    """Кем подписано письмо и куда придёт ответ."""

    #: Отображаемое имя отправителя. Пустое — значит показывать только адрес.
    display_name: str
    #: Адрес для ответа. `None` — заголовок не ставится вовсе.
    reply_to: str | None
    #: Подпись в конце тела письма.
    signature: str


def sanitize_header_text(value: str | None) -> str:
    """Привести текст к виду, безопасному для заголовка письма."""

    if not value:
        return ""
    return _SPACES.sub(" ", _CONTROL.sub(" ", value)).strip()


def _valid_address(value: str | None) -> str | None:
    cleaned = sanitize_header_text(value)
    return cleaned if cleaned and _ADDRESS.match(cleaned) else None


def build_mail_identity(brand: AppBrand) -> MailIdentity:
    """Собрать почтовую личность из действующего бренда.

    Адрес отправителя ЗДЕСЬ НЕ МЕНЯЕТСЯ и меняться не должен: письмо уходит с
    почтового узла платформы, и подстановка чужого домена в `From` провалила бы
    проверки SPF и DKIM — письма партнёра дружно ушли бы в спам. Поэтому
    подменяется то, что человек читает (имя отправителя и подпись), а ответ
    уводится на почту партнёра заголовком `Reply-To`. Полноценный адрес на
    домене партнёра — отдельный пункт 52.2 (домен/поддомен), и без него этот
    способ единственный честный.
    """

    return MailIdentity(
        display_name=sanitize_header_text(brand.app_name),
        reply_to=_valid_address(brand.support_email),
        signature=_signature(brand),
    )


def _signature(brand: AppBrand) -> str:
    """Подпись письма.

    Без неё письмо остаётся безымянным внутри: имя отправителя видно в списке
    писем, но в пересланном или распечатанном тексте — уже нет.
    """

    name = sanitize_header_text(brand.app_name)
    support = _valid_address(brand.support_email)
    lines = [f"— {name}" if name else ""]
    if support:
        lines.append(f"Поддержка: {support}")
    return "\n".join(line for line in lines if line)


def apply_signature(body: str, signature: str) -> str:
    """Добавить подпись к телу письма.

    Пустое тело подписью не «оживляем»: письмо без текста — это ошибка выше по
    течению, и подпись её замаскировала бы.
    """

    if not signature:
        return body
    if not (body or "").strip():
        return body
    return f"{body.rstrip()}\n\n{signature}\n"
