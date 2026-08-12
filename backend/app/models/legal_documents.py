"""BIZ-52 срез-5 (разд. 52.2): юридические тексты арендатора.

Оферта, политика обработки ПДн и текст согласия — то, что показывают ЧЕЛОВЕКУ.
Не путать с ``PdnConsent`` (SEC-66): там запись «субъект дал согласие», здесь —
сам текст, который ему показали.

**Версионируется, а не правится.** Каждая публикация создаёт новую строку с
``doc_version = предыдущая + 1``. Вопрос «какая редакция действовала в марте» —
юридический, и ответить на него можно только по неизменной истории. Тот же
приём, что у ``PdnConsent``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantBaseModel


class TenantLegalDocument(TenantBaseModel):
    """Одна редакция одного юридического текста арендатора."""

    __tablename__ = "tenant_legal_document"
    __table_args__ = (
        # Действующая редакция — с наибольшим `doc_version`. Уникальность пары
        # не даёт завести две «версии 3» и превратить вопрос «что действует» в
        # выбор из нескольких строк.
        UniqueConstraint(
            "tenant_id", "kind", "doc_version", name="uq_tenant_legal_kind_version"
        ),
        Index("ix_tenant_legal_kind", "tenant_id", "kind", "doc_version"),
    )

    #: `offer` / `privacy` / `consent` — список закрыт в
    #: `app.domains.reseller.legal.LegalDocumentKind`. Хранится строкой, а не
    #: native enum: добавление вида не должно требовать миграции типа в БД,
    #: а закрытость списка обеспечивает схема запроса.
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # НЕ `version`: это имя занято в TenantBaseModel под оптимистичную
    # блокировку, и SQLAlchemy сам увеличивает её при каждом UPDATE — номер
    # редакции сбивался бы при любой правке строки (грабля из PdnConsent).
    doc_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
