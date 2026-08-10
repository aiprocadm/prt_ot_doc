"""BIZ-50 срез-5 — выдача комплекта в кабинет клиента (Доп. №1, разд. 50.2 шаг 4).

ТЗ: «результат можно скачать, отправить в ЭДО или в кабинет клиента».
Скачивание работало. Кабинет — нет: контур генерации и контур кабинета жили
порознь, а кабинет клал в хранилище СТРОКУ «ZIP bundle for …» с типом
`application/zip`. Клиент скачивал файл, который не открывается ни одним
архиватором, и выглядело это как работающая выдача.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from sqlalchemy import select

from app.core.tenant import tenant_prefix_path
from app.models.models import RoleEnum
from app.models.packages import ClientPackagePreset, ClientPackageRun
from app.services.file_storage import FileStorageService

BASE = "/api/v1/packages"
#: Встроенный сценарий каталога — на нём проверяется, что портальный пресет
#: заводится сам и заводится один раз.
SCENARIO = "OT_NEW_EMPLOYEE"


def _real_archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("приказ.docx", "содержимое приказа")
    return buffer.getvalue()


async def _put_archive(sessionmaker, data_factory, key_suffix: str = "result.zip") -> tuple[str, str]:
    """Положить настоящий архив под префиксом арендатора. Возвращает (slug, ключ)."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        slug = tenant.slug
    key = f"{tenant_prefix_path(slug)}/packs/{key_suffix}"
    FileStorageService.default().put(key, _real_archive(), content_type="application/zip")
    return slug, key


@pytest.mark.anyio
async def test_client_downloads_the_real_archive(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    """Главная проверка среза: из кабинета скачивается НАСТОЯЩИЙ архив."""

    slug, key = await _put_archive(sessionmaker, data_factory)
    headers = {**(await make_auth_headers(RoleEnum.ADMIN)), "X-Tenant": slug}

    published = await async_client.post(
        f"{BASE}/publish",
        headers=headers,
        json={"preset_code": SCENARIO, "zip_storage_key": key},
    )
    assert published.status_code == 201, published.text
    run_id = published.json()["id"]

    link = await async_client.post(f"{BASE}/runs/{run_id}/portal-link", headers=headers)
    assert link.status_code == 200, link.text
    token = link.json()["portal_url"].split("token=", 1)[1]

    portal = await async_client.get(f"/api/v1/portal/packages/{run_id}", params={"token": token})
    assert portal.status_code == 200, portal.text
    files = {item["kind"]: item for item in portal.json()["files"]}
    assert "zip" in files, "комплекта в кабинете нет — выдавать нечего"
    assert files["zip"]["s3_key"] == key

    stored = FileStorageService.default().get(key)
    assert zipfile.is_zipfile(io.BytesIO(stored)), "клиенту отдан файл, который не является архивом"


@pytest.mark.anyio
async def test_foreign_archive_is_refused(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    """Без этой проверки арендатор опубликовал бы у себя ЧУЖОЙ архив по ключу."""

    slug, _ = await _put_archive(sessionmaker, data_factory)
    foreign_key = f"{tenant_prefix_path('someone-else')}/packs/result.zip"
    FileStorageService.default().put(foreign_key, _real_archive(), content_type="application/zip")

    headers = {**(await make_auth_headers(RoleEnum.ADMIN)), "X-Tenant": slug}
    response = await async_client.post(
        f"{BASE}/publish",
        headers=headers,
        json={"preset_code": SCENARIO, "zip_storage_key": foreign_key},
    )

    assert response.status_code == 403, response.text


@pytest.mark.anyio
async def test_missing_archive_is_refused(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    """Иначе в кабинете появилась бы запись «комплект выдан» со ссылкой в никуда."""

    slug, _ = await _put_archive(sessionmaker, data_factory)
    headers = {**(await make_auth_headers(RoleEnum.ADMIN)), "X-Tenant": slug}

    response = await async_client.post(
        f"{BASE}/publish",
        headers=headers,
        json={
            "preset_code": SCENARIO,
            "zip_storage_key": f"{tenant_prefix_path(slug)}/packs/нет-такого.zip",
        },
    )

    assert response.status_code == 404, response.text


@pytest.mark.anyio
async def test_unknown_scenario_is_refused(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    """Код вне каталога и вне пресетов — ошибка, а не повод придумать пресет."""

    slug, key = await _put_archive(sessionmaker, data_factory)
    headers = {**(await make_auth_headers(RoleEnum.ADMIN)), "X-Tenant": slug}

    response = await async_client.post(
        f"{BASE}/publish",
        headers=headers,
        json={"preset_code": "НЕТ-ТАКОГО", "zip_storage_key": key},
    )

    assert response.status_code == 404, response.text


@pytest.mark.anyio
async def test_second_publish_reuses_the_preset(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    """Пресет — проекция сценария на кабинет, а не новая запись на каждую выдачу."""

    slug, key = await _put_archive(sessionmaker, data_factory)
    headers = {**(await make_auth_headers(RoleEnum.ADMIN)), "X-Tenant": slug}
    body = {"preset_code": SCENARIO, "zip_storage_key": key}

    first = await async_client.post(f"{BASE}/publish", headers=headers, json=body)
    second = await async_client.post(f"{BASE}/publish", headers=headers, json=body)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text

    async with sessionmaker() as session:
        presets = (
            (
                await session.execute(
                    select(ClientPackagePreset).where(ClientPackagePreset.code == SCENARIO)
                )
            )
            .scalars()
            .all()
        )
        runs = (
            (
                await session.execute(
                    select(ClientPackageRun).where(ClientPackageRun.output_zip_s3_key == key)
                )
            )
            .scalars()
            .all()
        )
    assert len(presets) == 1, "каждая выдача плодит пресет"
    # Прогонов два — это правильно: две выдачи клиенту суть два события.
    assert len(runs) == 2


@pytest.mark.anyio
async def test_run_without_a_real_archive_has_no_zip(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    """Прогон без генерации больше НЕ подделывает архив.

    Раньше здесь в хранилище писалась строка «ZIP bundle for …» с типом
    `application/zip`. Отсутствие файла честнее файла, который не открывается.
    """

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(
            ClientPackagePreset(
                tenant_id=tenant.id,
                code="NO_ARCHIVE",
                name="Без архива",
                steps_json={"steps": [{"code": "collect_requirements"}]},
                required_inputs_json=[],
            )
        )
        await session.commit()
        slug = tenant.slug

    headers = {**(await make_auth_headers(RoleEnum.ADMIN)), "X-Tenant": slug}
    created = await async_client.post(
        f"{BASE}/runs", headers=headers, json={"preset_code": "NO_ARCHIVE"}
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]

    link = await async_client.post(f"{BASE}/runs/{run_id}/portal-link", headers=headers)
    token = link.json()["portal_url"].split("token=", 1)[1]
    portal = await async_client.get(f"/api/v1/portal/packages/{run_id}", params={"token": token})

    kinds = {item["kind"] for item in portal.json()["files"]}
    assert "zip" not in kinds, "кабинет снова выдаёт подделку вместо архива"
    assert "manifest" in kinds, "состав комплекта должен остаться виден"
