"""White-label: чей бренд носит приложение (Доп. №1 разд. 52.2).

Модуль `branding` покрывает бренд ДОКУМЕНТОВ и привязан к организации и
площадке внутри арендатора. Здесь — бренд САМОГО ПРИЛОЖЕНИЯ: имя в шапке и во
вкладке, цвет темы, служебная почта. Уровень другой (арендатор, а не
организация), и смысл другой: документ подписывает организация, а приложением
человека встречает партнёр, продавший платформу.

Наследование — три ступени, и порядок в них принципиален:

1. **свой бренд** — арендатор настроил себя сам;
2. **бренд партнёра** — клиент партнёра видит бренд того, у кого купил услугу;
3. **бренд платформы** — умолчание.

Ступень «партнёра» не пропускается даже тогда, когда у клиента есть частичная
настройка: незаполненные поля берутся выше по цепочке, а не падают сразу в
платформенное умолчание. Иначе клиент, поменявший ТОЛЬКО цвет, потерял бы имя
партнёра и увидел бы вендора — ровно то, что разд. 52.2 запрещает.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

#: Бренд платформы по умолчанию. Последняя ступень цепочки: если ни у клиента,
#: ни у партнёра ничего не настроено, приложение должно как-то называться.
DEFAULT_APP_NAME = "Платформа ОТ/ПБ"
#: Основной цвет темы в формате HSL-триплета Tailwind (`H S% L%`) — ровно в том
#: виде, в каком его ждёт CSS-переменная `--primary` в `index.css`. Хранить его
#: в другом формате значило бы переводить туда-обратно на каждой отрисовке и
#: однажды разойтись с интерфейсом.
DEFAULT_PRIMARY_COLOR = "222.2 47.4% 11.2%"


@dataclass(frozen=True)
class AppBrand:
    """Бренд приложения, каким его видит пользователь."""

    app_name: str
    primary_color: str
    support_email: str | None = None
    #: Кто дал этот бренд: `self` / `reseller` / `platform`. Не украшение —
    #: интерфейсу нужно знать, показывать ли партнёру пометку «бренд по
    #: умолчанию», а тестам приёмки — что наследование действительно сработало.
    source: str = "platform"


PLATFORM_BRAND = AppBrand(
    app_name=DEFAULT_APP_NAME,
    primary_color=DEFAULT_PRIMARY_COLOR,
    support_email=None,
    source="platform",
)


@dataclass(frozen=True)
class BrandOverride:
    """Настройка одного уровня. Пустое поле означает «не задано», а не «пусто»."""

    app_name: str | None = None
    primary_color: str | None = None
    support_email: str | None = None

    @property
    def is_empty(self) -> bool:
        return not any((self.app_name, self.primary_color, self.support_email))


def resolve_app_brand(
    *,
    own: BrandOverride | None,
    reseller: BrandOverride | None,
) -> AppBrand:
    """Собрать действующий бренд из цепочки «свой → партнёра → платформа».

    Поля собираются ПО ОТДЕЛЬНОСТИ: заполненное поле нижней ступени побеждает,
    незаполненное — уступает верхней. Цельная замена профиля («есть свой — берём
    только его») выглядела бы проще, но заставила бы каждого клиента, меняющего
    один цвет, переписывать имя и почту партнёра вручную.
    """

    brand = PLATFORM_BRAND
    source = "platform"

    for level, name in ((reseller, "reseller"), (own, "self")):
        if level is None or level.is_empty:
            continue
        brand = replace(
            brand,
            app_name=level.app_name or brand.app_name,
            primary_color=level.primary_color or brand.primary_color,
            support_email=level.support_email or brand.support_email,
        )
        source = name

    return replace(brand, source=source)
