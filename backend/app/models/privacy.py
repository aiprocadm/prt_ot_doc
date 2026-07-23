"""ПДн / 152-ФЗ (SEC-66 срез-1): журнал доступа к персональным данным субъекта.

Разд. 66.2 требует отвечать на вопрос «кто и когда обращался к ПДн субъекта» —
субъект (или клиент по договору) вправе запросить этот журнал. Общий `audit_log`
на эту роль не годится: он пишется по объекту действия и не индексируется по
субъекту ПДн, а хранит цепочку хешей всей активности арендатора.

Намеренно БЕЗ `SoftDeleteMixin`: журнал доступа к ПДн несмываемый — записи не
удаляются и не редактируются, только дописываются (append-only на уровне API:
писателя нет нигде, кроме `PdnAccessJournal.record`).

Таблица tenant-scoped, поэтому включена в RLS (SEC-65) — см.
`app/core/rls_policy.py` и миграцию `20260723_sec66_pdn_access_log`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantBaseModel

__all__ = ["PdnAccessLog", "PDN_ACCESS_ACTIONS"]

# Способы обращения к ПДн, которые журналируются. Расширяется по мере того, как
# новые поверхности начинают отдавать ПДн субъекта наружу.
PDN_ACCESS_ACTIONS: tuple[str, ...] = ("view_card", "export")


class PdnAccessLog(TenantBaseModel):
    __tablename__ = "pdn_access_log"
    __table_args__ = (
        Index(
            "ix_pdn_access_log_tenant_subject_occurred",
            "tenant_id",
            "subject_person_id",
            "occurred_at",
        ),
    )

    # Субъект ПДн — физлицо, чьи данные читали.
    subject_person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    # Кто читал. FK обнуляется при удалении пользователя, поэтому рядом лежит
    # снимок e-mail/роли — журнал должен пережить удаление учётной записи.
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(64), nullable=True)

    action: Mapped[str] = mapped_column(String(32), nullable=False)
    # Цель/правовое основание обращения (разд. 66.1) — свободный текст запроса.
    purpose: Mapped[str | None] = mapped_column(String(255), nullable=True)

    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
