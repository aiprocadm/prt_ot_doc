"""BIZ-52 срез-4 (разд. 52.2): бренд ПРИЛОЖЕНИЯ на уровне арендатора.

Отдельная таблица, а не поле в ``tenant.settings``: разд. 52.2 перечисляет
конкретные вещи (имя, цвет, почта поддержки, дальше — логотип, домен, юр.
тексты), и складывать их в свободный JSON значит отказаться от проверки типов и
от возможности спросить «у кого настроен бренд» одним запросом.

Не путать с модулем ``branding``: тот описывает бренд ДОКУМЕНТОВ и живёт на
уровне организации и площадки. Здесь — бренд самого приложения, уровень
арендатора. Документ подписывает организация, а приложением человека встречает
партнёр, продавший платформу.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantBaseModel


class TenantBranding(TenantBaseModel):
    """Настройка бренда приложения для одного арендатора.

    Строка НЕ обязана быть полной: незаполненное поле означает «не задано» и
    наследуется вверх по цепочке (свой → партнёра → платформа), см.
    ``app.domains.reseller.white_label``. Поэтому все поля nullable — заполнить
    их значениями по умолчанию значило бы намертво оборвать наследование
    у каждого, кто задал хотя бы одно поле.
    """

    __tablename__ = "tenant_branding"

    # Арендатор — это `tenant_id` из базовой модели. Уникальность на нём:
    # двух брендов у одного арендатора не бывает, а дубль строки сделал бы
    # ответ ручки неопределённым (грабля BIZ-61 срез-2, где семь тестовых
    # помощников делали add вместо update и получали два ответа на один вопрос).
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_branding_tenant"),)

    app_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: HSL-триплет в формате Tailwind (`H S% L%`) — ровно как ждёт CSS-переменная
    #: `--primary`. Перевод формата на каждой отрисовке однажды разошёлся бы с
    #: интерфейсом, и выглядело бы это как «тема не применилась».
    primary_color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    support_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Картинки живут В СТРОКЕ, а не в файловом контуре (BIZ-52 срез-6): общий
    # контур требует MinIO (в dev-lite выдача отвечает 503) и антивирусный
    # карантин, а логотип — маленькая публичная картинка с жёстким потолком
    # размера (`domains/reseller/brand_images.py`), которую надо отдавать
    # клиентам ЧУЖОГО арендатора (клиент партнёра видит логотип партнёра) —
    # общая выдача файлов такое запрещает намеренно.
    logo_image: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    #: Тип — из НАШЕГО распознавания по магическим байтам, не из заголовка
    #: клиента: заголовку верить нельзя (SVG под видом PNG = скрипт на странице
    #: входа каждого клиента).
    logo_media_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    favicon_image: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    favicon_media_type: Mapped[str | None] = mapped_column(String(64), nullable=True)


class TenantDomain(TenantBaseModel):
    """Собственный домен партнёра (BIZ-52 разд. 52.2, срез-189).

    ЧТО БЫЛО. Остаток строки звучал так: «домен и поддомен партнёра
    (инфраструктурный пункт: DNS и сертификаты вне кода)». DNS и сертификаты
    действительно снаружи. Но ВЛАДЕНИЕ доменом обязано подтверждаться кодом:
    иначе партнёр заявляет чужой домен, и платформа начинает отдавать под ним
    его бренд и его страницу входа.

    Подтверждение — TXT-запись с одноразовым словом: способ, который понимают
    все регистраторы и который не требует, чтобы домен уже куда-то указывал.

    Домен хранится в нижнем регистре и уникален ГЛОБАЛЬНО, а не в пределах
    арендатора: два арендатора с одним доменом — это спор о владении, а не
    две настройки.
    """

    __tablename__ = "tenant_domains"
    __table_args__ = (UniqueConstraint("domain", name="uq_tenant_domains_domain"),)

    domain: Mapped[str] = mapped_column(String(253), nullable=False, index=True)
    #: Одноразовое слово для TXT-записи `_ptd-verify.<домен>`.
    verification_token: Mapped[str] = mapped_column(String(64), nullable=False)
    #: pending | verified | failed. Строка, а не перечисление: набор состояний
    #: подтверждения меняется чаще, чем это стоит миграции типа.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Почему последняя проверка не удалась — человеку, а не в журнал.
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
