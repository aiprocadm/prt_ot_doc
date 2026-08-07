"""ПДн / 152-ФЗ (SEC-66 срез-3): реестр обработки и договоры поручения.

* :class:`PdnProcessingActivity` — разд. 66.1 «Реестр обработки: какие ПДн, цели,
  сроки, кто имеет доступ — **как данные в системе, не в Excel**». Одна строка =
  один процесс обработки (кадровый учёт, медосмотры, обучение…).
* :class:`PdnProcessingAgreement` — разд. 66.3 «Ролевая модель Оператор /
  Обработчик»: кто по 152-ФЗ Оператор, кто Обработчик, и каким договором поручения
  это оформлено. Аренда, аутсорсинг и reseller дают РАЗНЫЕ расклады ролей, поэтому
  роль хранится у каждого договора, а не одна на арендатора.

Обе таблицы tenant-scoped, поэтому армируются RLS (SEC-65) — см.
`app/core/rls_policy.py` и миграцию `20260728_sec66_pdn_registry_dpa`.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import TenantBaseModel

__all__ = [
    "PdnProcessingActivity",
    "PdnProcessingAgreement",
    "PDN_DATA_CATEGORIES",
    "PDN_SUBJECT_CATEGORIES",
    "PDN_PARTY_ROLES",
    "PDN_AGREEMENT_KINDS",
    "PDN_AGREEMENT_STATUSES",
]

# Категории ПДн. Разд. 66.1 требует отделять обычные от СПЕЦИАЛЬНЫХ: данные о
# здоровье (медосмотры) — специальная категория с повышенными требованиями, и
# в реестре это должно быть видно, а не подразумеваться.
PDN_DATA_CATEGORIES: tuple[str, ...] = (
    "regular",  # ФИО, контакты, должность, табельный номер
    "special_health",  # медосмотры, ограничения по здоровью
    "biometric",  # если появятся (сейчас платформа их не обрабатывает)
)

PDN_SUBJECT_CATEGORIES: tuple[str, ...] = (
    "employees",
    "contractor_employees",
    "candidates",
    "visitors",
)

# Роль АРЕНДАТОРА в конкретном договоре по 152-ФЗ.
PDN_PARTY_ROLES: tuple[str, ...] = ("operator", "processor")

# Модель отношений, из-за которой роли и расходятся (разд. 66.3).
PDN_AGREEMENT_KINDS: tuple[str, ...] = (
    "rent",  # аренда платформы: заказчик — Оператор, владелец платформы — Обработчик
    "outsourcing",  # аутсорсер обрабатывает ПДн сотрудников клиента
    "reseller",  # третий уровень ответственности
)

PDN_AGREEMENT_STATUSES: tuple[str, ...] = ("draft", "active", "terminated")


class PdnProcessingActivity(TenantBaseModel):
    """Строка реестра обработки ПДн (разд. 66.1).

    Отвечает на четыре вопроса регулятора одним объектом: КАКИЕ данные, С КАКОЙ
    целью и на каком основании, КАК ДОЛГО хранятся и КТО имеет доступ. Срок
    хранения — число месяцев плюс ссылка на норму: «3 года» без нормы в реестре
    бесполезно, потому что проверяют именно основание срока.
    """

    __tablename__ = "pdn_processing_activity"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_pdn_processing_activity_code"),
        Index("ix_pdn_processing_activity_tenant_active", "tenant_id", "is_active"),
    )

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    legal_basis: Mapped[str] = mapped_column(String(32), nullable=False, default="consent")

    data_categories: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    subject_categories: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )

    # Срок хранения. NULL = «до отзыва согласия / до прекращения основания».
    retention_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retention_basis: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Кто имеет доступ — роли платформы, а не поимённый список: состав людей
    # меняется, а ответ регулятору должен оставаться верным.
    access_roles: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    # Получатели вне арендатора (мед. организация, учебный центр, ФРДО…).
    recipients: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )

    # Локализация (разд. 66.1): где физически лежат данные. Строка, а не enum —
    # значение диктует хостинг, а не код.
    storage_location: Mapped[str] = mapped_column(String(64), nullable=False, default="RU")
    cross_border_transfer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Дата следующего пересмотра: реестр обязан жить, а не быть снимком на день сдачи.
    review_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PdnProcessingAgreement(TenantBaseModel):
    """Договор поручения обработки / фиксация ролей по 152-ФЗ (разд. 66.3).

    ``party_role`` — роль АРЕНДАТОРА в этом договоре. Один и тот же арендатор
    бывает Оператором по отношению к своим сотрудникам и Обработчиком по
    отношению к клиенту, которого обслуживает (аутсорсинг), — поэтому роль
    хранится у договора, а не одна на арендатора.
    """

    __tablename__ = "pdn_processing_agreement"
    __table_args__ = (Index("ix_pdn_processing_agreement_tenant_status", "tenant_id", "status"),)

    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    party_role: Mapped[str] = mapped_column(String(16), nullable=False)

    # Контрагент. Свободные поля: контрагент может не быть арендатором платформы.
    counterparty_name: Mapped[str] = mapped_column(String(255), nullable=False)
    counterparty_inn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Если контрагент — арендатор этой же платформы (reseller/аутсорсинг), связь
    # по слагу, без FK: тенант может быть удалён, а договор обязан пережить его.
    counterparty_tenant_slug: Mapped[str | None] = mapped_column(String(64), nullable=True)

    document_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")

    # Разрешено ли привлекать субобработчиков — ключевой пункт цепочки
    # «аутсорсер → reseller → платформа» (разд. 66.3).
    subprocessing_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Срок уведомления об утечке, согласованный сторонами (часы). Разд. 66.3
    # требует процедуры, а срок — единственная её машиночитаемая часть.
    breach_notification_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Какие процессы реестра покрывает договор — коды PdnProcessingActivity.
    covered_activity_codes: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
