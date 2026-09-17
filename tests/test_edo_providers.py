"""Сторож: отправка в ЭДО перестала быть тупиком (BIZ-50, срез-187).

ЧТО БЫЛО. ``POST /edo/send`` заканчивался честным отказом «провайдер не
настроен». Отказ был правильным решением своего времени — лучше, чем симуляция.
Но строка матрицы держала в остатке «отправка в ЭДО (после реализации
провайдера)»: что бы владелец ни настроил, кода для отправки НЕ СУЩЕСТВОВАЛО.

ЧТО ПРОВЕРЯЕТСЯ ЗДЕСЬ, по убыванию важности:

1. **Архив НАСТОЯЩИЙ.** В истории репозитория есть прямое предупреждение: раньше
   в хранилище клали строку «ZIP bundle for …» с типом ``application/zip``, и
   клиент скачивал файл, который не открывается ни одним архиватором. Здесь
   архив распаковывается, и в нём лежит сам документ.
2. **Выгрузка не выдаёт себя за доставку.** Оговорка о том, что получение
   адресатом не подтверждается, лежит ВНУТРИ пакета, а не только в ответе ручки:
   пакет живёт дольше ответа.
3. **Пустой документ — отказ, а не архив с одной описью.** Архив без документа
   выглядел бы как успешная выгрузка.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/test_edo_providers.py -v``.
"""

from __future__ import annotations

import io
import json
import stat
import sys
import zipfile
from types import SimpleNamespace

import pytest

from app.services import edo_providers as edo

PACKAGE = edo.EdoPackage(
    document_version_id="dv-1",
    file_key="tenant/t1/docs/instruction.docx",
    file_name="instruction.docx",
    recipient="ООО «Ромашка»",
    operator_code="diadoc",
    signatures=[{"id": "s1", "kind": "internal", "status": "signed", "signed_at": None}],
)


def _settings(**over) -> SimpleNamespace:
    base = {"edo_provider": "disabled", "edo_command": "", "edo_command_timeout_seconds": 5.0}
    base.update(over)
    return SimpleNamespace(**base)


def _script(tmp_path, body: str, name: str = "edo.py") -> str:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return f"{sys.executable} {path}"


def test_архив_настоящий_и_содержит_документ() -> None:
    """Главная проверка: файл открывается архиватором и внутри есть документ."""

    blob = edo.build_archive(PACKAGE, tenant_id="t1", document_bytes=b"PK-not-really-but-bytes")
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = set(archive.namelist())
        assert "instruction.docx" in names
        assert "manifest.json" in names
        assert "signatures/01.json" in names
        assert archive.read("instruction.docx") == b"PK-not-really-but-bytes"


def test_опись_говорит_что_доставка_не_подтверждается() -> None:
    """Оговорка лежит ВНУТРИ пакета: пакет живёт дольше ответа ручки."""

    blob = edo.build_archive(PACKAGE, tenant_id="t1", document_bytes=b"x")
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["document_version_id"] == "dv-1"
    assert manifest["recipient"] == "ООО «Ромашка»"
    assert "НЕ подтверждается" in manifest["note"]


def test_пустой_документ_это_отказ() -> None:
    """Архив с описью и без документа выглядел бы как успешная выгрузка."""

    with pytest.raises(edo.EdoDispatchError, match="собирать пакет не из чего"):
        edo.build_archive(PACKAGE, tenant_id="t1", document_bytes=b"")


def test_умолчание_оставляет_прежнее_поведение() -> None:
    """Кто ЭДО не подключал — не должен заметить изменения."""

    assert edo.provider_name(_settings()) == edo.DISABLED_PROVIDER
    assert edo.provider_name(SimpleNamespace()) == edo.DISABLED_PROVIDER


def test_опечатка_в_имени_поставщика_означает_выключено() -> None:
    assert edo.provider_name(_settings(edo_provider="diadoс")) == edo.DISABLED_PROVIDER


def test_внешняя_команда_получает_архив_и_возвращает_идентификатор(tmp_path) -> None:
    got = tmp_path / "got.zip"
    command = _script(
        tmp_path,
        "import sys, pathlib\n"
        f"pathlib.Path({str(got)!r}).write_bytes(sys.stdin.buffer.read())\n"
        "print('EDO-2026-0001')\n",
    )
    blob = edo.build_archive(PACKAGE, tenant_id="t1", document_bytes=b"doc")
    external_id = edo.dispatch_via_command(
        blob, package=PACKAGE, settings=_settings(edo_provider="command", edo_command=command)
    )
    assert external_id == "EDO-2026-0001"
    # Команда получила именно архив, а не описание архива.
    with zipfile.ZipFile(got) as archive:
        assert "instruction.docx" in archive.namelist()


def test_команда_без_идентификатора_это_отказ(tmp_path) -> None:
    """«Отправлено неизвестно что» хуже честной ошибки: отследить нечем."""

    command = _script(tmp_path, "pass")
    with pytest.raises(edo.EdoDispatchError, match="не вернул идентификатор"):
        edo.dispatch_via_command(
            b"zip", package=PACKAGE, settings=_settings(edo_provider="command", edo_command=command)
        )


def test_отказ_оператора_не_выдаётся_за_успех(tmp_path) -> None:
    command = _script(tmp_path, "import sys\nsys.stderr.write('bad inn')\nsys.exit(4)")
    with pytest.raises(edo.EdoDispatchError, match="отклонил пакет"):
        edo.dispatch_via_command(
            b"zip", package=PACKAGE, settings=_settings(edo_provider="command", edo_command=command)
        )


def test_команда_не_задана_это_отказ() -> None:
    with pytest.raises(edo.EdoDispatchError, match="EDO_COMMAND"):
        edo.dispatch_via_command(
            b"zip", package=PACKAGE, settings=_settings(edo_provider="command")
        )


def test_код_провайдера_выгрузки_говорящий() -> None:
    """Читающий журнал должен видеть, что это выгрузка, а не оператор."""

    assert "file" in edo.FILE_PROVIDER_CODE
    assert edo.FILE_PROVIDER_CODE != "diadoc"
