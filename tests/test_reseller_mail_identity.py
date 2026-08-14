"""Почтовая личность бренда (BIZ-52 срез-10, Доп. №1 разд. 52.2).

Правила без базы и без SMTP: подстановка чужого текста в заголовок письма — это
место, где ошибка не «выглядит некрасиво», а рвёт доставку или подделывает
письмо.
"""

from __future__ import annotations

from app.domains.reseller.mail_identity import (
    apply_signature,
    build_mail_identity,
    sanitize_header_text,
)
from app.domains.reseller.white_label import PLATFORM_BRAND, AppBrand


def _brand(**kwargs) -> AppBrand:
    base = dict(
        app_name="Охрана труда «Партнёр»",
        primary_color="222.2 47.4% 11.2%",
        support_email="help@partner.example",
        source="reseller",
    )
    base.update(kwargs)
    return AppBrand(**base)


def test_имя_бренда_становится_именем_отправителя():
    assert build_mail_identity(_brand()).display_name == "Охрана труда «Партнёр»"


def test_перевод_строки_в_имени_вычищается():
    # Схема бренда переводы строк ПРОПУСКАЕТ (там только ограничение длины), а
    # заголовок письма их не принимает: Python бросает ValueError, и отправка
    # всех писем клиентам этого партнёра падала бы из-за имени, скопированного
    # из документа вместе с переносом.
    identity = build_mail_identity(_brand(app_name="Партнёр\nBcc: chuzhoy@example.com"))

    assert "\n" not in identity.display_name
    assert identity.display_name == "Партнёр Bcc: chuzhoy@example.com"


def test_возврат_каретки_и_табуляция_тоже_вычищаются():
    assert sanitize_header_text("Имя\r\n\tс\tмусором") == "Имя с мусором"


def test_несколько_пробелов_схлопываются():
    assert sanitize_header_text("  Партнёр   и   Ко  ") == "Партнёр и Ко"


def test_пустое_имя_не_даёт_отображаемого():
    # Пустая строка в имени отправителя выглядела бы как письмо «от кого-то»:
    # лучше показать голый адрес, чем пустые кавычки.
    assert build_mail_identity(_brand(app_name="")).display_name == ""


def test_почта_поддержки_становится_адресом_ответа():
    assert build_mail_identity(_brand()).reply_to == "help@partner.example"


def test_кривая_почта_в_ответ_не_попадает():
    # Иначе мусор из настройки уехал бы в заголовок и сломал письмо целиком.
    for bad in ["не почта", "a@b", "", "две@почты@сразу.ru"]:
        assert build_mail_identity(_brand(support_email=bad)).reply_to is None


def test_без_почты_поддержки_заголовок_не_ставится():
    assert build_mail_identity(_brand(support_email=None)).reply_to is None


def test_подпись_называет_бренд_и_поддержку():
    signature = build_mail_identity(_brand()).signature

    assert signature == "— Охрана труда «Партнёр»\nПоддержка: help@partner.example"


def test_подпись_без_поддержки_только_имя():
    assert build_mail_identity(_brand(support_email=None)).signature == "— Охрана труда «Партнёр»"


def test_бренд_платформы_подписывает_платформой():
    # Прямой клиент платформы — обычный случай, а не сбой: письмо обязано быть
    # подписано, просто не партнёром.
    identity = build_mail_identity(PLATFORM_BRAND)

    assert identity.display_name == PLATFORM_BRAND.app_name
    assert identity.reply_to is None


def test_подпись_добавляется_в_конец_тела():
    assert apply_signature("Срок обучения истекает.", "— Партнёр") == (
        "Срок обучения истекает.\n\n— Партнёр\n"
    )


def test_пустое_тело_подписью_не_оживляется():
    # Письмо без текста — ошибка выше по течению; подпись её замаскировала бы.
    assert apply_signature("", "— Партнёр") == ""
    assert apply_signature("   ", "— Партнёр") == "   "


def test_без_подписи_тело_не_меняется():
    assert apply_signature("Текст", "") == "Текст"


# --- корень: в базу управляющие символы вообще не попадают ---------------------


def test_схема_бренда_чистит_переводы_строк():
    # Чистка в почте — защита от строк, сохранённых ДО этой правки. Новые не
    # должны появляться вовсе, иначе тот же мусор уедет в заголовок вкладки и в
    # шапку приложения.
    from app.schemas.white_label import TenantBrandingPatch

    patch = TenantBrandingPatch(
        app_name="Партнёр\nBcc: chuzhoy@example.com",
        primary_color=None,
        support_email="  help@partner.example  ",
    )

    assert patch.app_name == "Партнёр Bcc: chuzhoy@example.com"
    assert patch.support_email == "help@partner.example"


def test_имя_из_одних_пробелов_считается_незаданным():
    # Иначе наследование не вернулось бы: пустое имя победило бы имя партнёра.
    from app.schemas.white_label import TenantBrandingPatch

    assert TenantBrandingPatch(app_name="   ", primary_color=None).app_name is None
