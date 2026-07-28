"""ПДн / 152-ФЗ (SEC-66 срез-2): согласия субъекта и запись об обезличивании.

Дополняет срез-1 (`app/models/privacy.py` — журнал доступа):

* :class:`PdnConsent` — разд. 66.1 «правовые основания обработки: согласие субъекта
  либо иное основание; хранение и **версионирование** согласий».
* :class:`PdnErasureRecord` — разд. 66.2 «удаление / отзыв согласия: анонимизация или
  удаление; при этом сохранение обезличенных данных, где требует закон». Запись
  доказывает, ЧТО именно вычистили и ЧТО сохранили — без неё на вопрос субъекта
  «удалили ли мои данные» ответить нечем.

Обе таблицы tenant-scoped, поэтому армируются RLS (SEC-65) — см.
`app/core/rls_policy.py` и миграцию `20260728_sec66_pdn_consents_erasure`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import TenantBaseModel

__all__ = [
    "PdnConsent",
    "PdnErasureRecord",
    "PDN_LEGAL_BASES",
    "PDN_CONSENT_STATUSES",
    "PDN_CONSENT_PURPOSES",
]

# Правовые основания обработки (разд. 66.1). Согласие — лишь одно из них, и это
# принципиально: отзыв согласия НЕ обязывает стирать данные, которые обрабатываются
# по другому основанию (трудовой договор, требование закона о сроках хранения).
PDN_LEGAL_BASES: tuple[str, ...] = (
    "consent",  # согласие субъекта
    "contract",  # исполнение договора (трудового)
    "legal_obligation",  # требование закона (в т.ч. сроки хранения по ОТ)
    "vital_interests",  # защита жизненно важных интересов
)

PDN_CONSENT_STATUSES: tuple[str, ...] = (
    "active",
    "withdrawn",  # отозвано субъектом
    "superseded",  # заменено более новой версией
)

# Цели обработки — «реестр обработки как данные, а не Excel» (разд. 66.1).
PDN_CONSENT_PURPOSES: tuple[str, ...] = (
    "employment",  # кадровый учёт
    "occupational_safety",  # охрана труда: инструктажи, СИЗ, риски
    "medical_exams",  # медосмотры — СПЕЦИАЛЬНАЯ категория (здоровье)
    "training",  # обучение и аттестация
    "third_party_transfer",  # передача третьим лицам (аутсорсер/reseller)
)


class PdnConsent(TenantBaseModel):
    """Согласие субъекта на обработку ПДн для одной цели.

    **Версионируется, а не редактируется.** Новое согласие по той же цели создаёт
    строку с ``consent_version = предыдущая + 1``, а прежняя переходит в ``superseded``.
    Отзыв не удаляет строку, а ставит ``withdrawn`` + ``withdrawn_at``: доказать
    правомерность прошлой обработки можно только по неизменной истории.
    """

    __tablename__ = "pdn_consent"
    __table_args__ = (
        # Одна активная версия на (субъект, цель) — гарантия того, что «текущее
        # согласие» определяется однозначно, а не выбором из нескольких строк.
        Index(
            "ix_pdn_consent_tenant_subject_purpose",
            "tenant_id",
            "subject_person_id",
            "purpose",
        ),
        UniqueConstraint(
            "tenant_id",
            "subject_person_id",
            "purpose",
            "consent_version",
            name="uq_pdn_consent_subject_purpose_version",
        ),
    )

    subject_person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    legal_basis: Mapped[str] = mapped_column(String(32), nullable=False, default="consent")
    # НЕ ``version``: это имя занято в TenantBaseModel под оптимистичную блокировку
    # (``version_id_col``), и SQLAlchemy сам увеличивает её при каждом UPDATE — номер
    # версии согласия сбивался бы при любой правке строки.
    consent_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    # Что именно подписал субъект: ссылка на документ и хеш текста. Хранить сам
    # текст в каждой строке избыточно, а без хеша нельзя доказать, ЧТО подписали.
    document_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Срок действия. NULL = бессрочно/до отзыва.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Снимок оператора: FK обнуляется при удалении учётки, а история должна пережить её.
    recorded_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    recorded_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)


class PdnErasureRecord(TenantBaseModel):
    """Доказательство обезличивания субъекта (разд. 66.2).

    Обезличивание необратимо, поэтому единственный способ ответить субъекту и
    проверяющему «что именно сделали» — эта запись: перечень вычищенных полей и
    перечень разделов, оставленных обезличенными по требованию закона (сроки
    хранения по охране труда, медосмотрам, обучению).
    """

    __tablename__ = "pdn_erasure_record"
    __table_args__ = (
        Index("ix_pdn_erasure_record_tenant_subject", "tenant_id", "subject_person_id"),
    )

    subject_person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    # Псевдоним, которым заменены прямые идентификаторы. По нему можно связать
    # обезличенные записи между собой, не восстанавливая личность.
    pseudonym: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    scrubbed_fields: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    retained_sections: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    performed_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    performed_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
