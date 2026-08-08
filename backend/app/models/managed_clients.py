"""BIZ-49 (разд. 49.1): ORM-модель ведомого клиента аутсорсера.

Отдельный bounded context вне трёхтысячестрочного ``models.py`` (та же причина,
что у ``committees.py``). Native enums через ``native_enum`` — по дисциплине
enum-pg-label-parity.

**Клиент — не арендатор.** У одного аутсорсера-арендатора десятки ведомых
клиентов внутри его пространства, поэтому строка tenant-scoped. Ссылка на
собственного арендатора клиента (режим Dedicated) хранится СЛУГОМ, а не FK:
таблица арендаторов живёт в общей схеме, и жёсткая связь потянула бы
cross-schema FK, который проект уже однажды снимал (миграция wa02).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column

from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.base import SoftDeleteMixin, TenantBaseModel, native_enum


class ManagedClient(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "managed_client"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mode: Mapped[ManagedClientMode] = mapped_column(
        native_enum(ManagedClientMode, name="managedclientmode"), nullable=False
    )
    #: Организация клиента в пространстве аутсорсера (обязательна для Lightweight;
    #: у Dedicated остаётся ссылкой на историю после перевода).
    company_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("company.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    #: Слуг собственного арендатора клиента (режим Dedicated).
    dedicated_tenant_slug: Mapped[str | None] = mapped_column(String(64), nullable=True)

    contract_status: Mapped[ContractStatus] = mapped_column(
        native_enum(ContractStatus, name="managedclientcontractstatus"),
        nullable=False,
        default=ContractStatus.DRAFT,
    )
    contract_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contract_starts_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_ends_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: Ответственный специалист аутсорсера (загрузка по портфелю — разд. 49.2).
    responsible_person_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("person.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_managed_client_name"),
        Index("ix_managed_client_tenant_status", "tenant_id", "contract_status"),
    )


class ManagedClientAccess(TenantBaseModel):
    """BIZ-49 разд. 49.3: доступ специалиста аутсорсера к ведомому клиенту.

    Отзыв — ``revoked_at``, а не удаление строки: ТЗ требует трассируемости
    действий аутсорсера в данных клиента, а удалённый грант не отвечает на
    вопрос «имел ли он доступ, когда это сделал».
    """

    __tablename__ = "managed_client_access"

    managed_client_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("managed_client.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Специалист — именно ПОЛЬЗОВАТЕЛЬ (тот, кто входит), а не карточка сотрудника.
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Доступ ко всему клиенту объявляется явно; пустой список модулей — не «всё».
    all_modules: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    modules: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    granted_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        Index("ix_managed_client_access_client_user", "tenant_id", "managed_client_id", "user_id"),
        Index("ix_managed_client_access_user", "tenant_id", "user_id"),
    )


class ManagedClientContextSession(TenantBaseModel):
    """BIZ-49 срез-10 (Доп. №3, разд. 63.2): сессия работы «от имени клиента».

    До этого контекст был бессрочным: заголовок в запросе проверялся по гранту,
    и всё. ТЗ требует, чтобы работа «от имени» ИСТЕКАЛА (напр. через 60 минут),
    а выход из неё был событием на сервере, а не просто исчезнувшим баннером.

    Строка не удаляется при выходе — закрывается ``ended_at``. Журнал доступа к
    своим данным клиент вправе запросить (разд. 66), а удалённая сессия не
    отвечает на вопрос «кто и когда работал от моего имени».
    """

    __tablename__ = "managed_client_context_session"

    managed_client_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("managed_client.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Проставляется при выходе ИЛИ при отзыве доступа. Истечение по сроку
    #: здесь не пишется: его считает правило, иначе пришлось бы держать
    #: фоновую задачу, которая закрывает сессии ровно в минуту икс.
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        Index(
            "ix_mc_context_session_active",
            "tenant_id",
            "user_id",
            "managed_client_id",
            "started_at",
        ),
    )


class ManagedClientConsent(TenantBaseModel):
    """BIZ-49 срез-12 (разд. 49.3 + 66.3): согласие клиента на делегированный доступ.

    Аутсорсер обрабатывает ПДн сотрудников клиента — по 152-ФЗ нужны
    «согласия/поручения по цепочке». Строка фиксирует документ-основание;
    без действующей строки грант не выдаётся и контекст не открывается.

    Отзыв не удаляет строку — ставит ``revoked_at`` (след, как у грантов):
    «действовало ли согласие в момент работы специалиста» — вопрос, на который
    платформа обязана отвечать и после отзыва.
    """

    __tablename__ = "managed_client_consent"

    managed_client_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("managed_client.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Реквизиты документа-основания (номер поручения обработки / согласия).
    document_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    granted_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Срок из документа. Истёкшее согласие равно отозванному.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_mc_consent_client", "tenant_id", "managed_client_id", "granted_at"),
    )


class ManagedClientTransfer(TenantBaseModel):
    """BIZ-49 срез-14 (разд. 49.1): журнал переноса данных клиента.

    Фиксирует, что, когда и кем перенесено в арендатор клиента, включая
    соответствие старых и новых идентификаторов (``id_map``) — без него
    «сохранение timeline» превращается в угадывание, кто есть кто.
    Строка не удаляется: перенос — часть истории ведения клиента.
    """

    __tablename__ = "managed_client_transfer"

    managed_client_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("managed_client.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_tenant_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="completed")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    #: Сколько чего скопировано: {"company": 1, "people": N, "people_skipped": M}.
    counts: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    #: Соответствие старых id -> новых: {"company": {old: new}, "people": {old: new}}.
    id_map: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
