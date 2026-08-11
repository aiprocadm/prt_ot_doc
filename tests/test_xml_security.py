"""XXE / billion-laughs hardening tests (Дополнение №3 к ТЗ, разд. 64.2).

Аудит кода нашёл реальную уязвимость: ``etree.fromstring(content)`` в
``app.modules.replace.engine_xml`` (и других парсерах XML из загруженных DOCX)
по умолчанию уязвим к XXE (чтение файлов сервера / SSRF через внешние сущности)
и billion-laughs (DoS через экспоненциальное раздувание сущностей).

Эти тесты пинят контракт общего гарда ``app.core.xml_security``:
* внешняя сущность НЕ читает файл сервера;
* billion-laughs НЕ раздувает память (парсинг отвергается сразу);
* легитимный OOXML по-прежнему парсится.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from app.core.xml_security import (
    XmlSecurityError,
    lxml_fromstring,
    secure_lxml_parser,
    stdlib_fromstring,
)
from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# Уникальный маркер «секрета сервера»: если XXE сработает, он утечёт в дерево.
_SECRET_MARKER = "TOP_SECRET_XXE_CANARY_9f3a"

_BENIGN_XML = (
    f"<?xml version='1.0'?>"
    f"<w:document xmlns:w='{W_NS}'>"
    f"<w:body><w:p><w:r><w:t>Привет &amp; пока</w:t></w:r></w:p></w:body>"
    f"</w:document>"
).encode("utf-8")


def _xxe_payload(secret_path: str) -> bytes:
    """DOCX-XML с внешней сущностью, ссылающейся на файл сервера."""
    return (
        "<?xml version='1.0'?>"
        "<!DOCTYPE root [<!ENTITY xxe SYSTEM 'file://" + secret_path + "'>]>"
        f"<w:document xmlns:w='{W_NS}'>"
        "<w:body><w:p><w:r><w:t>&xxe;</w:t></w:r></w:p></w:body>"
        "</w:document>"
    ).encode("utf-8")


_BILLION_LAUGHS = (
    "<?xml version='1.0'?>"
    "<!DOCTYPE lolz [<!ENTITY lol 'lol'>"
    "<!ENTITY lol2 '&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;'>"
    "<!ENTITY lol3 '&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;'>"
    "<!ENTITY lol4 '&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;'>]>"
    "<root>&lol4;</root>"
).encode("utf-8")


# -----------------------------------------------------------------------------
# 1. Guard layer — DOCTYPE/DTD отвергается для обоих парсеров
# -----------------------------------------------------------------------------


@pytest.fixture()
def secret_file(tmp_path):
    path = tmp_path / "server_secret.txt"
    path.write_text(_SECRET_MARKER, encoding="utf-8")
    # lxml ждёт POSIX-подобный путь в file://; на Windows нормализуем разделители.
    return str(path).replace("\\", "/")


def test_lxml_rejects_external_entity(secret_file: str) -> None:
    with pytest.raises(XmlSecurityError):
        lxml_fromstring(_xxe_payload(secret_file))


def test_stdlib_rejects_external_entity(secret_file: str) -> None:
    with pytest.raises(XmlSecurityError):
        stdlib_fromstring(_xxe_payload(secret_file))


def test_lxml_rejects_billion_laughs() -> None:
    # Должно упасть на гарде мгновенно — без разворачивания сущностей.
    with pytest.raises(XmlSecurityError):
        lxml_fromstring(_BILLION_LAUGHS)


def test_stdlib_rejects_billion_laughs() -> None:
    with pytest.raises(XmlSecurityError):
        stdlib_fromstring(_BILLION_LAUGHS)


def test_guard_is_case_insensitive_and_tolerates_whitespace() -> None:
    payload = b"<?xml version='1.0'?><!  doctype x ><root/>"
    with pytest.raises(XmlSecurityError):
        stdlib_fromstring(payload)


# -----------------------------------------------------------------------------
# 2. Parser layer — даже если DOCTYPE обошёл гард, файл сервера не читается
# -----------------------------------------------------------------------------


def test_secure_lxml_parser_never_reads_server_file(secret_file: str) -> None:
    """Второй рубеж: жёсткий парсер не разворачивает внешнюю сущность.

    Скармливаем DOCTYPE напрямую парсеру (в обход строкового гарда) и убеждаемся,
    что содержимое секретного файла НЕ попало в дерево — либо парсер отверг
    сущности исключением, либо оставил ссылку неразвёрнутой.
    """
    parser = secure_lxml_parser()
    try:
        root = etree.fromstring(_xxe_payload(secret_file), parser=parser)
    except etree.XMLSyntaxError:
        return  # парсер отказался обрабатывать сущность — тоже безопасно
    serialized = etree.tostring(root, encoding="unicode")
    assert _SECRET_MARKER not in serialized


# -----------------------------------------------------------------------------
# 3. Integration — вредоносный DOCX через replace_xml_parts не читает файл
# -----------------------------------------------------------------------------


def _docx_with_xml(document_xml: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


def test_replace_engine_blocks_malicious_docx(secret_file: str) -> None:
    from app.modules.replace.engine_xml import replace_xml_parts

    malicious = _docx_with_xml(_xxe_payload(secret_file))
    with pytest.raises(XmlSecurityError):
        replace_xml_parts(
            malicious,
            [{"from": "a", "to": "b"}],
            case_sensitive=False,
            whole_word=False,
        )


# -----------------------------------------------------------------------------
# 4. No regression — легитимный OOXML по-прежнему парсится
# -----------------------------------------------------------------------------


def test_lxml_parses_benign_ooxml() -> None:
    root = lxml_fromstring(_BENIGN_XML)
    text = root.find(f".//{{{W_NS}}}t").text
    assert text == "Привет & пока"  # предопределённая сущность &amp; развёрнута


def test_stdlib_parses_benign_ooxml() -> None:
    root = stdlib_fromstring(_BENIGN_XML)
    assert root.find(f".//{{{W_NS}}}t").text == "Привет & пока"
