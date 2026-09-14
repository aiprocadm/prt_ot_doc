"""Сторож ЖИВОЙ ручки отправки в ЭДО (BIZ-50, срез-187).

ПОЧЕМУ ОТДЕЛЬНО ОТ `tests/test_edo_providers.py`. Тот файл проверяет сборку
пакета — чистые функции без базы. Этого мало, и срез-187 доказал это на себе:
служба была зелёной, а ручка падала, потому что перечисление направления
называется ``OUTGOING``, а в коде ручки стояло ``OUTBOUND``. Ошибку поймала не
проверка, а ручной запуск. Теперь её ловит этот файл.

УРОК ОБЩИЙ: тесты «шва» не заменяют теста ТОГО МЕСТА, где шов подключён.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/api/test_edo_send_file_export.py -v``.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi import status

from app.services.file_storage import FileStorageService


@pytest.mark.asyncio
async def test_выгрузка_файлом_собирает_настоящий_архив(
    async_client, sessionmaker, make_auth_headers, data_factory, monkeypatch
):
    """Поставщик `file`: ручка отдаёт ключ архива, а архив открывается."""

    from app.core import config as config_module

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _, version = await data_factory.create_document(tenant=tenant, session=session)

    # Кладём настоящий файл документа в хранилище: без него выгрузка обязана
    # отказать, и это проверяется отдельным тестом ниже.
    storage = FileStorageService.default()
    storage.put(version.file_key, b"PK real document bytes", content_type="application/octet-stream")

    settings = config_module.get_settings()
    monkeypatch.setattr(settings, "edo_provider", "file", raising=False)

    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/edo/send",
        json={"document_version_id": version.id, "recipient": "ООО «Ромашка»"},
        headers=headers,
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert body["artifact_key"], "ручка не вернула ключ выгруженного пакета"
    assert body["status"] == "sent"
    # Ответ прямо говорит, что доставка НЕ подтверждается.
    assert "НЕ подтверждается" in body["detail"]

    blob = storage.get(body["artifact_key"])
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = archive.namelist()
        assert "manifest.json" in names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["document_version_id"] == version.id
        assert manifest["recipient"] == "ООО «Ромашка»"
        # Сам документ внутри, а не только опись.
        assert any(name != "manifest.json" and not name.startswith("signatures/") for name in names)


@pytest.mark.asyncio
async def test_без_файла_документа_ручка_отказывает(
    async_client, sessionmaker, make_auth_headers, data_factory, monkeypatch
):
    """Пакет без документа не имеет права выглядеть успешной выгрузкой."""

    from app.core import config as config_module

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _, version = await data_factory.create_document(tenant=tenant, session=session)

    settings = config_module.get_settings()
    monkeypatch.setattr(settings, "edo_provider", "file", raising=False)

    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/edo/send",
        json={"document_version_id": version.id},
        headers=headers,
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["detail"]["code"] in {
        "EDO_DOCUMENT_FILE_MISSING",
        "EDO_DISPATCH_FAILED",
    }


@pytest.mark.asyncio
async def test_умолчание_сохраняет_прежний_отказ(
    async_client, sessionmaker, make_auth_headers, data_factory
):
    """Кто ЭДО не подключал — не должен заметить изменения."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _, version = await data_factory.create_document(tenant=tenant, session=session)

    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/edo/send",
        json={"document_version_id": version.id, "provider_code": "mock"},
        headers=headers,
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["detail"]["code"] == "EDO_PROVIDER_NOT_CONFIGURED"
