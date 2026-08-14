"""Манифест приложения под брендом (BIZ-52 срез-14, Доп. №1 разд. 52.2)."""

from __future__ import annotations

from app.domains.reseller.pwa_manifest import (
    DEFAULT_THEME_COLOR,
    build_manifest,
    hsl_triplet_to_hex,
    short_name_for,
)
from app.domains.reseller.white_label import PLATFORM_BRAND, AppBrand


def _brand(**kwargs) -> AppBrand:
    base = dict(
        app_name="Охрана труда Партнёр",
        primary_color="222.2 47.4% 11.2%",
        support_email=None,
        source="reseller",
    )
    base.update(kwargs)
    return AppBrand(**base)


def test_имя_бренда_становится_именем_приложения():
    assert build_manifest(_brand(), has_logo=False, tenant_slug="acme")["name"] == (
        "Охрана труда Партнёр"
    )


def test_цвет_темы_переводится_в_понятный_браузеру():
    # Браузер не понимает формат CSS-переменной `H S% L%`, в котором цвет
    # хранится у нас: без перевода тема ярлыка осталась бы пустой.
    assert hsl_triplet_to_hex("222.2 47.4% 11.2%") == "#0f172a"
    assert hsl_triplet_to_hex("0 0% 100%") == "#ffffff"


def test_непонятный_цвет_даёт_умолчание_а_не_поломку():
    assert hsl_triplet_to_hex("синий") == DEFAULT_THEME_COLOR
    assert hsl_triplet_to_hex(None) == DEFAULT_THEME_COLOR


def test_короткое_имя_берёт_первое_слово():
    # «Охрана труда Партнёр» под ярлыком читалось бы как «Охрана…»; первое
    # слово честнее обрезанной фразы.
    assert short_name_for("Охрана труда Партнёр") == "Охрана"


def test_короткое_имя_не_трогает_и_так_короткое():
    assert short_name_for("Партнёр") == "Партнёр"


def test_очень_длинное_первое_слово_обрезается():
    assert short_name_for("Электроэнергетика Плюс") == "Электроэнерг"


def test_логотип_партнёра_становится_иконкой():
    icons = build_manifest(_brand(), has_logo=True, tenant_slug="acme")["icons"]

    # Со слагом: манифест и иконки браузер грузит без заголовков приложения, и
    # без слага сервер отдал бы логотип другого арендатора.
    assert icons[0]["src"] == "/api/v1/public/branding/logo?tenant=acme"


def test_без_логотипа_иконка_партнёра_не_подставляется():
    # Ссылка на несуществующую картинку сделала бы ярлык пустым — это заметнее
    # и хуже, чем иконка платформы.
    icons = build_manifest(_brand(), has_logo=False, tenant_slug="acme")["icons"]

    assert all("branding/logo" not in icon["src"] for icon in icons)


def test_запасные_иконки_остаются_всегда():
    icons = build_manifest(_brand(), has_logo=True, tenant_slug="acme")["icons"]

    assert any(icon["purpose"] == "maskable" for icon in icons)


def test_бренд_платформы_даёт_платформенный_манифест():
    manifest = build_manifest(PLATFORM_BRAND, has_logo=False, tenant_slug=None)

    assert manifest["name"] == PLATFORM_BRAND.app_name
    assert manifest["display"] == "standalone"


def test_описание_называет_бренд_а_не_вендора():
    manifest = build_manifest(_brand(), has_logo=False, tenant_slug="acme")

    assert "Охрана труда Партнёр" in manifest["description"]
    assert "PRT" not in manifest["description"]
