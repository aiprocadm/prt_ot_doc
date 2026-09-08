"""HTML-версия письма выводится из текста (BIZ-54-57 срез-122).

ЗАЧЕМ. Письма уходили одним простым текстом: в почтовом клиенте это стена
строк, где период, сводка и список дел выглядят одинаково, и отчёт директору
читают по диагонали. Оформление добавлено так, чтобы у письма НЕ появилось
двух редакций: HTML собирается из того же текста.
"""

from __future__ import annotations

import re

from app.services.mail_html import render_plain_as_html


def _text(html: str) -> str:
    """Разметку долой — остаётся то, что увидит человек."""

    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def test_ничего_не_теряется_из_текста() -> None:
    """Главное свойство: HTML не может сказать меньше, чем текст."""

    body = "Отчёт за период.\n\nНарушений 12.\n\nЧто нужно сделать:\n— Продлить\n— Выдать"

    видно = _text(render_plain_as_html(body))

    for кусок in ("Отчёт за период.", "Нарушений 12.", "Что нужно сделать:", "Продлить", "Выдать"):
        assert кусок in видно


def test_первая_строка_становится_заголовком() -> None:
    html = render_plain_as_html("О чём письмо.\n\nПодробности.")

    assert "font-weight:600" in html.split("</p>")[0]
    assert "О чём письмо." in html.split("</p>")[0]


def test_пункты_собираются_в_список() -> None:
    html = render_plain_as_html("Что сделать:\n— Раз\n— Два\n— Три")

    assert html.count("<li>") == 3
    # Заголовок списка остался отдельным абзацем, а не первым пунктом.
    assert "<p" in html.split("<ul")[0]


def test_одинокое_тире_это_подпись_а_не_список() -> None:
    """Так подписывают письмо; список из одного пункта не встречается."""

    html = render_plain_as_html("Текст письма.\n\n— Охрана труда «Партнёр»")

    assert "<ul" not in html
    assert "— Охрана труда «Партнёр»" in _text(html)


def test_данные_экранируются() -> None:
    """В тело идут данные арендатора — вставленная разметка не должна ожить."""

    html = render_plain_as_html('Отчёт <script>alert("x")</script> и 5 < 7.')

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "5 &lt; 7" in html


def test_переносы_внутри_абзаца_сохраняются() -> None:
    html = render_plain_as_html("Первая строка\nвторая строка\n\nНовый абзац")

    assert "<br>" in html
    assert html.count("<p") == 3 or html.count("<p") == 2


def test_пустое_тело_не_даёт_пустой_вёрстки() -> None:
    """Письмо без текста — ошибка выше по течению, и оформление её не маскирует."""

    assert render_plain_as_html("") == ""
    assert render_plain_as_html("   \n\n  ") == ""


def test_стили_только_строчные() -> None:
    """Почтовые клиенты вырезают <style> и внешние таблицы стилей."""

    html = render_plain_as_html("Текст.\n\n— Пункт один\n— Пункт два")

    assert "<style" not in html
    assert "class=" not in html
    assert 'style="' in html


def test_ссылок_не_выдумывается() -> None:
    """Адреса приложения у сервера нет — выдуманная ссылка хуже её отсутствия."""

    html = render_plain_as_html("Подробности на дашборде (/dashboard).")

    assert "<a " not in html
    assert "http" not in html
