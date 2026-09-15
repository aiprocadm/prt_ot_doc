"""ORM models describing normative legal acts and their clauses."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SharedModel

__all__ = ["NpaAct", "NpaClause", "NpaRevision"]


class NpaAct(SharedModel):
    """Нормативный акт: общий реестр платформы ИЛИ локальный акт арендатора.

    Срез-201 (B.18 разд. 19.1). До него реестр знал только акты, заведённые
    владельцем платформы (федеральные), а свой приказ или инструкцию арендатор
    записать не мог вовсе — и вся обвязка (редакции, пункты, связи, требования,
    оценка влияния) была для них недоступна.

    **Почему локальный акт живёт в ЭТОЙ таблице, а не в своей.** Связи
    (``NPABinding.npa_id``) и требования (``ComplianceRequirement.npa_id``)
    ссылаются на ``npa_act.id``, и целостность держит настоящий внешний ключ
    (миграция ``20260910_b18_npabinding_npa_act``). Отдельная таблица для
    локальных актов означала бы либо вторую копию всей обвязки, либо
    полиморфную ссылку без внешнего ключа — то есть потерю той самой
    целостности, которую срез-142 специально добавлял.

    **Цена решения названа честно: это ОБЩАЯ таблица, и RLS к ней не
    применяется.** Поэтому видимость держится не базой, а единственным местом в
    коде — ``app.domains.npa.scope.visible_acts``; любой запрос к ``NpaAct``
    обязан идти через него, и это стережёт тест
    ``tests/test_npa_scope_guard.py``. Пропущенный фильтр здесь означает, что
    один арендатор видит приказы другого.
    """

    __tablename__ = "npa_act"

    #: Два ЧАСТИЧНЫХ уникальных индекса вместо одного обычного.
    #:
    #: Обычный ``UNIQUE(owner_tenant_id, code)`` тут не годится: и PostgreSQL, и
    #: SQLite считают NULL не равным самому себе, поэтому два федеральных акта с
    #: одним кодом (оба с ``owner_tenant_id IS NULL``) такой индекс ПРОПУСТИТ —
    #: ровно ту защиту, которая была в реестре с первого дня, мы бы и потеряли.
    #: Поэтому случая два, и каждый закрыт своим индексом.
    __table_args__ = (
        Index(
            "uq_npa_act_registry_code",
            "code",
            unique=True,
            postgresql_where=text("owner_tenant_id IS NULL"),
            sqlite_where=text("owner_tenant_id IS NULL"),
        ),
        Index(
            "uq_npa_act_owner_code",
            "owner_tenant_id",
            "code",
            unique=True,
            postgresql_where=text("owner_tenant_id IS NOT NULL"),
            sqlite_where=text("owner_tenant_id IS NOT NULL"),
        ),
    )

    #: NULL — общий реестр платформы (виден всем). Иначе — локальный акт
    #: арендатора: виден только ему.
    #: Отдельный индекс не нужен: составной ``uq_npa_act_owner_code`` начинается
    #: с этой же колонки и обслуживает поиск «мои акты».
    owner_tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    #: Код уникален В ПРЕДЕЛАХ ВЛАДЕЛЬЦА, а не глобально: «Приказ №1» бывает у
    #: каждого арендатора, и глобальная уникальность отдавала бы этот код
    #: первому, кто успел. Разделение на два частичных индекса — в миграции:
    #: в PostgreSQL ``UNIQUE`` считает NULL различными, поэтому один составной
    #: индекс пропустил бы два федеральных акта с одним кодом.
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    edition: Mapped[str] = mapped_column(String(128), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    revisions: Mapped[list["NpaRevision"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="NpaRevision.effective_from"
    )

    clauses: Mapped[list["NpaClause"]] = relationship(
        back_populates="act",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="NpaClause.code",
    )


class NpaRevision(SharedModel):
    """Revision history for a normative legal act."""

    __tablename__ = "npa_revision"

    act_id: Mapped[str] = mapped_column(
        ForeignKey("npa_act.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision_code: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("act_id", "revision_code", name="uq_npa_revision_per_act"),)


class NpaClause(SharedModel):
    """Article or clause belonging to a normative legal act."""

    __tablename__ = "npa_clause"

    act_id: Mapped[str] = mapped_column(
        ForeignKey("npa_act.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    act: Mapped[NpaAct] = relationship(back_populates="clauses")

    __table_args__ = (UniqueConstraint("act_id", "code", name="uq_npa_clause_code_per_act"),)
