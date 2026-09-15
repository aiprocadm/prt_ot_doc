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

__all__ = ["PdnAccessLog", "PdnBreach", "PDN_ACCESS_ACTIONS"]

# Способы обращения к ПДн, которые журналируются. Расширяется по мере того, как
# новые поверхности начинают отдавать ПДн субъекта наружу.
PDN_ACCESS_ACTIONS: tuple[str, ...] = (
    "view_card",
    "export",
    # SEC-66 срез-2: изменения ПДн и работа с основаниями обработки тоже подлежат
    # учёту — «кто обращался к ПДн» включает того, кто их правил и стирал.
    "rectify",
    "consent_grant",
    "consent_withdraw",
    "anonymize",
)


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


class PdnBreach(TenantBaseModel):
    """Утечка персональных данных: обязательство со сроками (разд. 66.3, срез-207).

    ЧЕГО ЗДЕСЬ НЕТ И НЕ БУДЕТ: отправки уведомления в Роскомнадзор. Канала для
    неё не существует — уведомление подают через форму регулятора. Кнопка
    «уведомить», которая на деле только ставит галочку, была бы худшей из
    возможных: человек решит, что дело сделано. Здесь ведётся обязательство с
    вычислимым сроком, а факт отправки отмечает человек (тот же приём, что у
    удаления из резервных копий, срез-188).

    Сроки НЕ хранятся числами: они считаются при чтении из момента обнаружения
    (``app.modules.privacy.breach``). Записанный срок через сутки после правки
    даты обнаружения молча разошёлся бы с законом.
    """

    __tablename__ = "pdn_breach"

    #: Когда утечку ОБНАРУЖИЛИ. Именно от этого момента закон считает 24 и 72
    #: часа — не от момента самой утечки. Вводит человек: платформа не может
    #: знать, когда ему написали или позвонили.
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Когда утечка произошла, если это удалось установить. Пусто — «не
    #: установлено»: это законное состояние, а не пробел.
    happened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    summary: Mapped[str] = mapped_column(String(512), nullable=False)
    #: Сколько человек затронуто, если установлено. Пусто — «пока не считали».
    affected_people: Mapped[int | None] = mapped_column(nullable=True)

    #: Три ОТДЕЛЬНЫХ факта. Уведомить регулятора, сообщить результаты
    #: расследования и уведомить людей — разные обязательства, и одна галочка
    #: на все три означала бы, что выполнив лёгкое, организация считает
    #: закрытым и трудное.
    regulator_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    findings_reported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    subjects_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    registered_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (Index("ix_pdn_breach_tenant_discovered", "tenant_id", "discovered_at"),)
