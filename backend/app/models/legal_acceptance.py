"""BIZ-52 срез-11 (разд. 52.2): кто и когда принял юридический текст.

Срез-5 дал публикацию текстов, эта таблица даёт доказательство акцепта: какой
человек, какую редакцию и когда принял.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantBaseModel


class TenantLegalAcceptance(TenantBaseModel):
    """Одно принятие одной редакции одним пользователем.

    **Запись неизменяема.** Принятие не редактируется и не отзывается: «я
    согласился 14 августа» — исторический факт, а не текущее состояние. Вышла
    новая редакция — появляется новая строка.
    """

    __tablename__ = "tenant_legal_acceptance"
    __table_args__ = (
        # Один человек принимает одну редакцию один раз. Без этого двойное
        # нажатие кнопки давало бы две записи, и «когда принял» превращалось бы
        # в выбор из нескольких ответов.
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "kind",
            "doc_version",
            name="uq_tenant_legal_acceptance_user_kind_version",
        ),
        Index("ix_tenant_legal_acceptance_lookup", "tenant_id", "user_id", "kind"),
    )

    #: Подписывает ЧЕЛОВЕК, а не арендатор: оферта — договор с тем, кто нажал
    #: кнопку, и запись «арендатор принял» не отвечает на вопрос кто именно.
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    doc_version: Mapped[int] = mapped_column(Integer, nullable=False)

    #: Чья редакция принята: `self` / `reseller` / `platform`. Без этого поля
    #: номер редакции неоднозначен — у клиента и у партнёра свои нумерации, и
    #: «версия 3» означала бы разные тексты.
    source: Mapped[str] = mapped_column(String(16), nullable=False)

    #: Отпечаток принятого текста.
    #:
    #: Ссылки на строку документа здесь НАМЕРЕННО НЕТ: клиент принимает оферту
    #: ПАРТНЁРА, то есть строку другого арендатора — внешний ключ через границу
    #: арендаторов под FORCE RLS (SEC-65) прочитать нельзя, а удаление партнёра
    #: увело бы за собой доказательство. Отпечаток отвечает «какой именно текст»
    #: независимо от судьбы исходной строки.
    body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
