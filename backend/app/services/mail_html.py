"""HTML-версия письма — из того же текста, что и обычная (BIZ-54-57 срез-122).

Письма уходили одним простым текстом: в почтовом клиенте это стена строк, где
период, сводка и список дел выглядят одинаково. Отчёт директору так читают
по диагонали и пропускают главное.

## Решения

**1. HTML НЕ пишется отдельно — он выводится из текста.** Иначе у письма
появились бы две редакции одного сообщения, и первая же правка текста
оставила бы HTML со старыми словами. Здесь ровно наоборот: текст — источник,
HTML — его оформление. Разойтись им не на чем.

**2. Оформление, а не выдумка.** Отрисовщик не пытается понять смысл: он
делит текст на абзацы по пустой строке, собирает подряд идущие строки с
тире в список и выделяет первую строку как заголовок. Никаких ссылок,
картинок и кнопок: адреса приложения у сервера нет (в настройках его просто
не существует), а выдуманная ссылка в письме — худший вид лжи.

**3. Обычный текст остаётся всегда.** Письмо уходит как
``multipart/alternative``: клиент без HTML (и почтовый архив) видит прежний
текст слово в слово. HTML-только письмо было бы шагом назад.

**4. Всё экранируется.** В тело попадают данные арендатора — название
организации, сводка, пункты «что сделать». Без экранирования угловая скобка
в названии сломала бы вёрстку, а вставка разметки показала бы получателю
чужой текст как часть письма.

**5. Стили — только строчные (inline).** Почтовые клиенты вырезают ``<style>``
и внешние таблицы стилей; всё, что должно быть видно, стоит в атрибуте
самого элемента.
"""

from __future__ import annotations

from html import escape

__all__ = ["render_plain_as_html"]

#: Строчные стили: почтовые клиенты вырезают всё остальное (решение 5).
_WRAP = (
    "font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
    "font-size:14px;line-height:1.5;color:#1f2937;max-width:640px"
)
_HEADING = "font-size:16px;font-weight:600;margin:0 0 12px 0;color:#111827"
_PARAGRAPH = "margin:0 0 12px 0"
_LIST = "margin:0 0 12px 0;padding-left:20px"

#: Чем в тексте помечают пункт списка. Тире — то, что уже пишут письма
#: отчётов (`client_report_mail.build_letter`), дефис и звёздочка — на случай
#: других отправителей.
_BULLETS = ("— ", "- ", "* ", "• ")


def _is_bullet(line: str) -> bool:
    return line.startswith(_BULLETS)


def _strip_bullet(line: str) -> str:
    for mark in _BULLETS:
        if line.startswith(mark):
            return line[len(mark) :]
    return line


def _render_block(block: list[str]) -> str:
    """Абзац или список — из подряд идущих строк.

    Одна строка с тире списком НЕ становится: так подписывают письмо
    («— Охрана труда «Партнёр»»), и маркер там значит подпись, а не пункт.
    Список из одного пункта в письме не встречается.
    """

    if len(block) > 1 and all(_is_bullet(line) for line in block):
        items = "".join(f"<li>{escape(_strip_bullet(line))}</li>" for line in block)
        return f'<ul style="{_LIST}">{items}</ul>'
    text = "<br>".join(escape(line) for line in block)
    return f'<p style="{_PARAGRAPH}">{text}</p>'


def render_plain_as_html(body: str) -> str:
    """Оформить готовый текст письма как HTML.

    Возвращает фрагмент ``<div>…</div>``: письмо собирает ``EmailProvider``,
    он же добавляет его альтернативной частью к тексту.
    """

    lines = (body or "").replace("\r\n", "\n").split("\n")
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                blocks.append(current)
                current = []
            continue
        # Список начинается с новой строки, даже если абзац не кончился:
        # «Что нужно сделать:» и пункты под ним — разные блоки.
        if current and _is_bullet(stripped) != _is_bullet(current[0]):
            blocks.append(current)
            current = []
        current.append(stripped)
    if current:
        blocks.append(current)

    if not blocks:
        return ""

    parts: list[str] = []
    first = blocks[0]
    # Первая строка — о чём письмо; в тексте она и так стоит первой строкой.
    if len(first) == 1 and not _is_bullet(first[0]):
        parts.append(f'<p style="{_HEADING}">{escape(first[0])}</p>')
        blocks = blocks[1:]
    parts.extend(_render_block(block) for block in blocks)
    return f'<div style="{_WRAP}">' + "".join(parts) + "</div>"
