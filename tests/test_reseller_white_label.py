"""BIZ-52 срез-4: чей бренд носит приложение (разд. 52.2).

Правила чистые — проверяются примерами без базы.
"""

from __future__ import annotations

from app.domains.reseller.white_label import (
    DEFAULT_APP_NAME,
    DEFAULT_PRIMARY_COLOR,
    BrandOverride,
    resolve_app_brand,
)

PARTNER = BrandOverride(
    app_name="Охрана труда «Партнёр»",
    primary_color="210 90% 40%",
    support_email="help@partner.ru",
)


class TestЦепочкаНаследования:
    def test_без_настроек_бренд_платформы(self) -> None:
        brand = resolve_app_brand(own=None, reseller=None)
        assert brand.app_name == DEFAULT_APP_NAME
        assert brand.primary_color == DEFAULT_PRIMARY_COLOR
        assert brand.source == "platform"

    def test_клиент_партнёра_видит_бренд_партнёра(self) -> None:
        brand = resolve_app_brand(own=None, reseller=PARTNER)
        assert brand.app_name == "Охрана труда «Партнёр»"
        assert brand.support_email == "help@partner.ru"
        assert brand.source == "reseller"

    def test_свой_бренд_побеждает_бренд_партнёра(self) -> None:
        brand = resolve_app_brand(own=BrandOverride(app_name="ООО «Своё имя»"), reseller=PARTNER)
        assert brand.app_name == "ООО «Своё имя»"
        assert brand.source == "self"

    def test_незаполненные_поля_берутся_у_партнёра_а_не_у_платформы(self) -> None:
        """Главное правило среза.

        Клиент поменял ТОЛЬКО цвет. Если незаполненное имя упадёт сразу в
        платформенное умолчание, он увидит вендора — ровно то, что разд. 52.2
        запрещает.
        """

        brand = resolve_app_brand(own=BrandOverride(primary_color="0 80% 50%"), reseller=PARTNER)
        assert brand.primary_color == "0 80% 50%"
        assert brand.app_name == "Охрана труда «Партнёр»"
        assert brand.support_email == "help@partner.ru"

    def test_пустая_настройка_ступень_не_занимает(self) -> None:
        """Заведённая, но не заполненная строка не должна «съедать» наследование."""

        brand = resolve_app_brand(own=BrandOverride(), reseller=PARTNER)
        assert brand.app_name == "Охрана труда «Партнёр»"
        assert brand.source == "reseller"

    def test_пустая_настройка_партнёра_отдаёт_платформу(self) -> None:
        brand = resolve_app_brand(own=None, reseller=BrandOverride())
        assert brand.app_name == DEFAULT_APP_NAME
        assert brand.source == "platform"

    def test_частичный_бренд_партнёра_дополняется_платформой(self) -> None:
        brand = resolve_app_brand(own=None, reseller=BrandOverride(app_name="Только имя"))
        assert brand.app_name == "Только имя"
        assert brand.primary_color == DEFAULT_PRIMARY_COLOR
        assert brand.source == "reseller"


class TestИсточникБренда:
    def test_источник_называет_нижнюю_сработавшую_ступень(self) -> None:
        assert resolve_app_brand(own=PARTNER, reseller=PARTNER).source == "self"
        assert resolve_app_brand(own=None, reseller=PARTNER).source == "reseller"
        assert resolve_app_brand(own=None, reseller=None).source == "platform"


class TestФорматЦвета:
    def test_умолчание_совпадает_с_переменной_интерфейса(self) -> None:
        """Цвет хранится ровно в том виде, в каком его ждёт CSS-переменная.

        Переводи формат туда-обратно — и однажды бэкенд с интерфейсом разойдутся
        на одном значении, а выглядеть это будет как «тема не применилась».
        """

        assert DEFAULT_PRIMARY_COLOR == "222.2 47.4% 11.2%"
