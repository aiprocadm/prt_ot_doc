"""BIZ-52 срез-6: распознавание картинок бренда (разд. 52.2, первый пункт).

Правила чистые — проверяются байтами без HTTP.
"""

from __future__ import annotations

import pytest

from app.domains.reseller.brand_images import (
    FAVICON_MEDIA_TYPES,
    LOGO_MEDIA_TYPES,
    detect_image_media_type,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 16
ICO = b"\x00\x00\x01\x00" + b"\x00" * 16
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


class TestРаспознаваниеФормата:
    @pytest.mark.parametrize(
        ("data", "expected"),
        [
            (PNG, "image/png"),
            (JPEG, "image/jpeg"),
            (WEBP, "image/webp"),
            (ICO, "image/x-icon"),
        ],
    )
    def test_настоящие_форматы_узнаются(self, data: bytes, expected: str) -> None:
        assert detect_image_media_type(data) == expected

    def test_svg_не_считается_картинкой(self) -> None:
        """SVG умеет содержать скрипты — на публичной выдаче это XSS."""

        assert detect_image_media_type(SVG) is None

    def test_мусор_не_считается_картинкой(self) -> None:
        assert detect_image_media_type(b"\x00\x01\x02\x03garbage") is None

    def test_пустые_байты_не_считаются_картинкой(self) -> None:
        assert detect_image_media_type(b"") is None

    def test_короткий_riff_без_webp_не_проходит(self) -> None:
        """`RIFF` — общий контейнер (в нём и WAV): без метки WEBP это не картинка."""

        assert detect_image_media_type(b"RIFF\x00\x00\x00\x00WAVE") is None


class TestСписокФорматов:
    def test_svg_нет_ни_в_одном_списке(self) -> None:
        assert "image/svg+xml" not in LOGO_MEDIA_TYPES
        assert "image/svg+xml" not in FAVICON_MEDIA_TYPES

    def test_favicon_строже_логотипа(self) -> None:
        """WebP-иконку не понимает Safari — «не показывается» выглядело бы нашей поломкой."""

        assert "image/webp" in LOGO_MEDIA_TYPES
        assert "image/webp" not in FAVICON_MEDIA_TYPES
