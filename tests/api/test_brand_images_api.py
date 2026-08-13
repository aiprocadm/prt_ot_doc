"""BIZ-52 срез-6: логотип и favicon по HTTP (разд. 52.2, первый пункт).

Закрепляется главное: картинка отдаётся БЕЗ токена (её ждёт экран входа),
клиент партнёра видит картинку ПАРТНЁРА, формат распознаётся по содержимому,
а не по заголовку клиента, и SVG не проходит ни под каким именем.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.domains.reseller import RESELLER_KIND
from app.domains.reseller.brand_images import LOGO_MAX_BYTES
from app.models.models import RoleEnum, Tenant

PUBLIC = "/api/v1/public/branding"
OWN = "/api/v1/platform/branding"

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
ICO = b"\x00\x00\x01\x00" + b"\x00" * 32
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


async def _shape_tree() -> dict[str, str]:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        rows = {
            record.slug: record
            for record in (
                (
                    await session.execute(
                        select(Tenant).where(Tenant.slug.in_(["beta", "acme", "zeta"]))
                    )
                )
                .scalars()
                .all()
            )
        }
        rows["beta"].kind = RESELLER_KIND
        rows["acme"].parent_id = rows["beta"].id
        rows["zeta"].parent_id = None
        await session.commit()
        return {slug: record.id for slug, record in rows.items()}


async def _partner_headers(make_auth_headers) -> dict[str, str]:
    return await make_auth_headers(
        RoleEnum.ADMIN, tenant="beta", email="admin-beta-logo@example.com"
    )


async def _upload(async_client, headers, *, kind: str = "logo", data: bytes = PNG,
                  content_type: str = "image/png"):
    return await async_client.put(
        f"{OWN}/{kind}",
        headers=headers,
        files={"file": (f"brand.{kind}", data, content_type)},
    )


@pytest.mark.anyio
async def test_логотип_партнёра_виден_его_клиенту_без_токена(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()
    uploaded = await _upload(async_client, await _partner_headers(make_auth_headers))
    assert uploaded.status_code == 200, uploaded.text

    response = await async_client.get(f"{PUBLIC}/logo", headers={"x-tenant": "acme"})

    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["content-type"].startswith("image/png")
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.anyio
async def test_признак_логотипа_появляется_в_бренде(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()
    await _upload(async_client, await _partner_headers(make_auth_headers))

    response = await async_client.get(PUBLIC, headers={"x-tenant": "acme"})

    body = response.json()
    assert body["has_logo"] is True
    assert body["has_favicon"] is False


@pytest.mark.anyio
async def test_чужой_арендатор_логотип_партнёра_не_получает(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()
    await _upload(async_client, await _partner_headers(make_auth_headers))

    response = await async_client.get(f"{PUBLIC}/logo", headers={"x-tenant": "zeta"})

    assert response.status_code == 404


@pytest.mark.anyio
async def test_favicon_принимает_ico(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()
    uploaded = await _upload(
        async_client,
        await _partner_headers(make_auth_headers),
        kind="favicon",
        data=ICO,
        content_type="image/x-icon",
    )
    assert uploaded.status_code == 200, uploaded.text

    response = await async_client.get(f"{PUBLIC}/favicon", headers={"x-tenant": "acme"})

    assert response.status_code == 200
    assert response.content == ICO


@pytest.mark.anyio
async def test_svg_отклоняется_даже_под_видом_png(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Заголовок клиента — просто строка; SVG на публичной выдаче — XSS."""

    await _shape_tree()

    response = await _upload(
        async_client,
        await _partner_headers(make_auth_headers),
        data=SVG,
        content_type="image/png",
    )

    assert response.status_code == 422
    assert response.json()["code"] == "BRAND_IMAGE_FORMAT_UNSUPPORTED"


@pytest.mark.anyio
async def test_заголовок_клиента_игнорируется_в_обе_стороны(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Настоящий PNG с нелепым заголовком принимается: решают байты."""

    await _shape_tree()

    response = await _upload(
        async_client,
        await _partner_headers(make_auth_headers),
        data=PNG,
        content_type="text/plain",
    )

    assert response.status_code == 200, response.text
    served = await async_client.get(f"{PUBLIC}/logo", headers={"x-tenant": "beta"})
    assert served.headers["content-type"].startswith("image/png")


@pytest.mark.anyio
async def test_webp_не_годится_в_favicon(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Safari не понимает WebP-иконки — «не показывается» выглядело бы нашей поломкой."""

    await _shape_tree()
    webp = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 16

    response = await _upload(
        async_client,
        await _partner_headers(make_auth_headers),
        kind="favicon",
        data=webp,
        content_type="image/webp",
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_потолок_размера_обрывает_загрузку(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()
    oversized = PNG + b"\x00" * LOGO_MAX_BYTES

    response = await _upload(
        async_client, await _partner_headers(make_auth_headers), data=oversized
    )

    assert response.status_code == 413
    assert response.json()["code"] == "BRAND_IMAGE_TOO_LARGE"


@pytest.mark.anyio
async def test_обычный_арендатор_картинки_не_грузит(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()
    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="acme", email="admin-acme-logo@example.com"
    )

    response = await _upload(async_client, headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FLEET_ACCESS_FORBIDDEN"


@pytest.mark.anyio
async def test_загрузка_без_токена_отклоняется(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()

    response = await _upload(async_client, {"x-tenant": "beta"})

    assert response.status_code == 401


@pytest.mark.anyio
async def test_удаление_возвращает_наследование(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Убрал свой логотип — клиент снова без картинки, а не с «пустой»."""

    await _shape_tree()
    headers = await _partner_headers(make_auth_headers)
    await _upload(async_client, headers)

    removed = await async_client.delete(f"{OWN}/logo", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["has_logo"] is False

    response = await async_client.get(f"{PUBLIC}/logo", headers={"x-tenant": "acme"})
    assert response.status_code == 404


@pytest.mark.anyio
async def test_повторная_загрузка_заменяет_а_не_плодит(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()
    headers = await _partner_headers(make_auth_headers)
    await _upload(async_client, headers, data=PNG)
    second = PNG + b"\x11" * 8
    await _upload(async_client, headers, data=second)

    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        from app.models.white_label import TenantBranding

        rows = (
            (
                await session.execute(
                    select(TenantBranding).where(TenantBranding.tenant_id == ids["beta"])
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].logo_image == second


@pytest.mark.anyio
async def test_повторный_запрос_с_etag_отвечает_304(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Favicon запрашивается на каждый заход — без 304 каждый заход стоил бы перекачки."""

    await _shape_tree()
    await _upload(async_client, await _partner_headers(make_auth_headers))

    first = await async_client.get(f"{PUBLIC}/logo", headers={"x-tenant": "acme"})
    etag = first.headers["etag"]

    second = await async_client.get(
        f"{PUBLIC}/logo", headers={"x-tenant": "acme", "if-none-match": etag}
    )

    assert second.status_code == 304
    assert second.content == b""


@pytest.mark.anyio
async def test_картинка_и_текст_наследуются_независимо(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Партнёр загрузил ТОЛЬКО логотип — картинка его, а текст платформенный.

    Наследование по отдельности: пустые текстовые поля партнёра не занимают
    ступень (это закреплено срезом-4), но его картинка при этом ЖИВЁТ — иначе
    «загрузи логотип» тайно требовало бы заполнить и имя.
    """

    await _shape_tree()
    partner = await _partner_headers(make_auth_headers)
    await _upload(async_client, partner)

    response = await async_client.get(PUBLIC, headers={"x-tenant": "acme"})

    body = response.json()
    # Текстовых полей партнёр не задавал — текст честно платформенный…
    assert body["source"] == "platform"
    # …а картинка — партнёрская, независимо от текста.
    assert body["has_logo"] is True