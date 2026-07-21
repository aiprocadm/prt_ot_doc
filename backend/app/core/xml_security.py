"""Безопасный парсинг XML из загруженных файлов (Дополнение №3 к ТЗ, разд. 64.2).

Загруженные DOCX/XLSX — это ZIP-архивы с XML внутри. Парсеры ``lxml`` и
``xml.etree.ElementTree`` в конфигурации по умолчанию уязвимы:

* **XXE** — внешняя сущность вида ``<!ENTITY x SYSTEM "file:///etc/passwd">``
  позволяет прочитать файлы сервера или сходить в закрытую сеть (SSRF).
  ``lxml`` по умолчанию РАЗВОРАЧИВАЕТ такие сущности.
* **billion-laughs** — вложенные внутренние сущности раздуваются экспоненциально
  и приводят к отказу в обслуживании (DoS) по памяти/CPU.

Оба класса атак требуют объявления DTD/DOCTYPE (только так задаются кастомные
сущности). Легитимный OOXML DOCTYPE не содержит — поэтому единый входной гард,
отвергающий DOCTYPE, закрывает обе атаки сразу. Для ``lxml`` дополнительно
отключаем разворачивание сущностей и сеть (defense-in-depth).

Использовать ВЕЗДЕ, где парсится XML из загруженных пользователем файлов —
вместо прямых вызовов ``etree.fromstring`` / ``ET.fromstring``.
"""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from lxml import etree

__all__ = [
    "XmlSecurityError",
    "secure_lxml_parser",
    "lxml_fromstring",
    "stdlib_fromstring",
]

# DOCTYPE/DTD в OOXML (DOCX/XLSX) легитимно не встречается. Его наличие —
# индикатор XXE/billion-laughs. Дешёвый первый рубеж: отсекаем на входе,
# не дав парсеру дойти до объявления сущностей. ``re.IGNORECASE`` — на случай
# нестандартного регистра; допускаем пробелы после ``<!``.
_DOCTYPE_RE = re.compile(rb"<!\s*DOCTYPE", re.IGNORECASE)


class XmlSecurityError(ValueError):
    """XML содержит запрещённую конструкцию (DOCTYPE/DTD) — вероятная XXE-атака.

    Наследуемся от ``ValueError``, чтобы существующие обработчики, ловящие
    ошибки парсинга как ``ValueError``, продолжали работать без изменений.
    """


def _as_bytes(content: bytes | str) -> bytes:
    return content if isinstance(content, bytes) else content.encode("utf-8")


def _guard_doctype(content: bytes | str) -> None:
    """Отвергнуть XML с объявлением DTD/DOCTYPE до его разбора."""
    if _DOCTYPE_RE.search(_as_bytes(content)):
        raise XmlSecurityError(
            "XML содержит DOCTYPE/DTD — запрещено (возможна XXE или billion-laughs)"
        )


def secure_lxml_parser() -> etree.XMLParser:
    """Жёсткий ``lxml``-парсер: без внешних сущностей, сети и загрузки DTD.

    * ``resolve_entities=False`` — сущности не разворачиваются (нет XXE и
      billion-laughs, даже если DOCTYPE как-то проскочил гард).
    * ``no_network=True`` — запрет обращений в сеть за DTD/сущностями (SSRF).
    * ``load_dtd=False`` / ``dtd_validation=False`` — DTD не подгружается.
    * ``huge_tree=False`` — включены штатные лимиты libxml2 на размер дерева.
    """
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
    )


def lxml_fromstring(content: bytes | str) -> etree._Element:
    """Безопасная замена ``lxml.etree.fromstring`` для XML из загруженных файлов."""
    _guard_doctype(content)
    return etree.fromstring(content, parser=secure_lxml_parser())


def stdlib_fromstring(content: bytes | str) -> ET.Element:
    """Безопасная замена ``xml.etree.ElementTree.fromstring``.

    Stdlib-парсер (expat) по умолчанию не тянет внешние сущности/DTD, но остаётся
    уязвим к billion-laughs через внутренние сущности. Явный гард по DOCTYPE
    закрывает и это, не требуя стороннего ``defusedxml``.
    """
    _guard_doctype(content)
    return ET.fromstring(content)
