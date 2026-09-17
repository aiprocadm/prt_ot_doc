"""Манифест приложения под брендом арендатора (BIZ-52 срез-14, разд. 52.2).

Срезы 4, 6 и 10 подменили брендом всё, что человек видит внутри приложения и в
письмах. Осталось самое заметное: манифест PWA. Он задавался на сборке —
`name: "PRT OT SaaS Platform"`, иконки вендора, — поэтому клиент партнёра,
добавивший приложение на домашний экран телефона, получал ярлык с именем
вендора. Разд. 52.2 требует «скрытия любых упоминаний исходного вендора», а
экран телефона — ровно то место, где эта подмена нужнее всего.

Правила здесь чистые: на входе бренд, на выходе словарь манифеста.
"""

from __future__ import annotations

import re

from app.domains.reseller.white_label import AppBrand

#: Цвет темы в манифесте задаётся обычным HEX: браузеры не понимают формат
#: CSS-переменной `H S% L%`, в котором цвет хранится у нас.
_HSL_TRIPLET = re.compile(r"^(\d{1,3}(?:\.\d+)?)\s+(\d{1,3}(?:\.\d+)?)%\s+(\d{1,3}(?:\.\d+)?)%$")

#: Запасной цвет — тот же, что стоял в собранном манифесте до этого среза.
DEFAULT_THEME_COLOR = "#0f172a"
DEFAULT_BACKGROUND_COLOR = "#f8fafc"

#: Короткое имя обрезается: под ярлыком на телефоне помещается мало, и длинное
#: имя система обрежет сама — лучше сделать это осмысленно.
SHORT_NAME_LIMIT = 12


def hsl_triplet_to_hex(triplet: str | None) -> str:
    """Перевести цвет бренда в HEX. Непонятное значение — цвет по умолчанию."""

    match = _HSL_TRIPLET.match((triplet or "").strip())
    if match is None:
        return DEFAULT_THEME_COLOR
    hue = float(match.group(1))
    saturation = float(match.group(2)) / 100
    lightness = float(match.group(3)) / 100
    chroma = (1 - abs(2 * lightness - 1)) * saturation
    second = chroma * (1 - abs((hue / 60) % 2 - 1))
    shift = lightness - chroma / 2
    if hue < 60:
        parts = (chroma, second, 0.0)
    elif hue < 120:
        parts = (second, chroma, 0.0)
    elif hue < 180:
        parts = (0.0, chroma, second)
    elif hue < 240:
        parts = (0.0, second, chroma)
    elif hue < 300:
        parts = (second, 0.0, chroma)
    else:
        parts = (chroma, 0.0, second)
    return "#" + "".join(f"{round((value + shift) * 255):02x}" for value in parts)


def short_name_for(app_name: str) -> str:
    """Короткое имя для ярлыка.

    Берём первое слово, если оно само по себе достаточно короткое: «Охрана
    труда Партнёр» на ярлыке читается как «Охрана…», и первое слово честнее
    обрезанной фразы.
    """

    cleaned = " ".join(app_name.split())
    if len(cleaned) <= SHORT_NAME_LIMIT:
        return cleaned
    first_word = cleaned.split(" ", 1)[0]
    if len(first_word) <= SHORT_NAME_LIMIT:
        return first_word
    return cleaned[:SHORT_NAME_LIMIT].rstrip()


def build_manifest(brand: AppBrand, *, has_logo: bool, tenant_slug: str | None) -> dict:
    """Собрать манифест под бренд арендатора.

    Иконка берётся партнёрская, только если логотип действительно загружен:
    ссылка на несуществующую картинку сделала бы ярлык пустым, а это заметнее
    и хуже, чем ярлык с иконкой платформы.

    Адрес иконки несёт слаг арендатора: манифест и его иконки браузер грузит
    БЕЗ заголовков приложения, и без слага сервер отдал бы логотип не того
    арендатора.
    """

    icons: list[dict] = []
    if has_logo and tenant_slug:
        icons.append(
            {
                "src": f"/api/v1/public/branding/logo?tenant={tenant_slug}",
                "sizes": "any",
                "type": "image/png",
                "purpose": "any",
            }
        )
    icons.extend(
        [
            {
                "src": "/pwa-icon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any",
            },
            {
                "src": "/mask-icon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "maskable",
            },
        ]
    )
    return {
        "name": brand.app_name,
        "short_name": short_name_for(brand.app_name),
        "description": f"{brand.app_name}: охрана труда, промбезопасность, экология и документооборот.",
        "theme_color": hsl_triplet_to_hex(brand.primary_color),
        "background_color": DEFAULT_BACKGROUND_COLOR,
        "display": "standalone",
        "start_url": "/",
        "scope": "/",
        "icons": icons,
    }
