"""ed02: DROP мёртвых легаси-таблиц подписания ``signatures`` и ``edo_envelopes``.

ЭДО Срез-1 (ed01 + PR #649) перевёл подпись на ПЭП-ядро (signature_requests):

  * ``signatures`` (создана 20250425_edo_approval_signature_mvp) — писателей
    не осталось: edo_workflow.create_signature/sign_submit пишут через
    PepSigningService, читатели sign_status/list_signatures переведены на
    SignatureRequest. ORM-класс Signature удалён из
    app/models/approval_workflow.py этим же срезом.
  * ``edo_envelopes`` (создана 20260303_next30_approval_signing_core) — была
    носителем симуляции SENT→DELIVERED в approval_signing_v1; после честной
    чистки (/edo:send → 409 EDO_PROVIDER_NOT_CONFIGURED) ни писателей, ни
    читателей. ORM-класс EdoEnvelope удалён из app/models/models.py.

Upgrade дропает обе таблицы (FK между ними нет; их индексы уходят вместе с
таблицами на PG и SQLite) и подчищает осиротевшие PG enum-типы
``signaturetype``/``signaturestatus`` (использовались только колонками
``signatures``) и ``edoenvelopestatus`` (только ``edo_envelopes``).
``ENUM.create/drop(checkfirst=True)`` — no-op на SQLite (там enum = VARCHAR).

Downgrade честно воссоздаёт обе таблицы в состоянии «на позиции ed02 в цепочке»:

  * ``signatures`` — verbatim из 20250425_edo_approval_signature_mvp
    (ретрофитов не было; в т.ч. БЕЗ колонки ``version`` — известный
    ORM-дрейф, iter29 эту таблицу не ретрофитил) + её 2 индекса;
  * ``edo_envelopes`` — из 20260303_next30 + колонка ``version``
    server_default="1" (20260528_iter29) + server_default="queued" на
    ``status`` (20260529_iter38; его downgrade сбросит default позже по пути
    к base — round-trip симметрия) + её 2 индекса.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260612_ed02_drop_legacy_signing_tables"
down_revision = "20260611_ed01_pep_signing_columns"
branch_labels = None
depends_on = None

# Независимые таблицы (FK между ними нет) — порядок не критичен.
DROPPED_TABLES = (
    "signatures",  # Signature (approval_workflow.py, удалён)
    "edo_envelopes",  # EdoEnvelope (models.py, удалён)
)

# PG enum-типы, осиротевшие после DROP (создавались create_type=False,
# поэтому create/drop здесь явные; на SQLite оба вызова — no-op).
signature_type = postgresql.ENUM(
    "KEP",
    "UNEP",
    "INTERNAL",
    name="signaturetype",
    create_type=False,
)
signature_status = postgresql.ENUM(
    "pending",
    "signed",
    "failed",
    name="signaturestatus",
    create_type=False,
)
edo_envelope_status = postgresql.ENUM(
    "queued",
    "sent",
    "delivered",
    "signed",
    "rejected",
    "failed",
    name="edoenvelopestatus",
    create_type=False,
)


def upgrade() -> None:
    op.drop_table("signatures")
    op.drop_table("edo_envelopes")

    bind = op.get_bind()
    signature_status.drop(bind, checkfirst=True)
    signature_type.drop(bind, checkfirst=True)
    edo_envelope_status.drop(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    signature_type.create(bind, checkfirst=True)
    signature_status.create(bind, checkfirst=True)
    edo_envelope_status.create(bind, checkfirst=True)

    # --- signatures: verbatim из 20250425_edo_approval_signature_mvp ------
    op.create_table(
        "signatures",
        sa.Column("document_version_id", sa.String(length=36), nullable=False),
        sa.Column("type", signature_type, nullable=False),
        sa.Column("status", signature_status, nullable=False),
        sa.Column("signer_user_id", sa.String(length=36), nullable=True),
        sa.Column("cert_info_json", sa.JSON(), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("receipts_s3_key", sa.String(length=512), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_version_id"], ["documentversion.id"]),
        sa.ForeignKeyConstraint(["signer_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signatures_document", "signatures", ["tenant_id", "document_version_id"])
    op.create_index("ix_signatures_status", "signatures", ["tenant_id", "status"])

    # --- edo_envelopes: next30 + iter29 (version) + iter38 (default) ------
    op.create_table(
        "edo_envelopes",
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("status", edo_envelope_status, nullable=False, server_default="queued"),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_edo_envelopes_status", "edo_envelopes", ["tenant_id", "status"])
    op.create_index(
        "ix_edo_envelopes_object", "edo_envelopes", ["tenant_id", "object_type", "object_id"]
    )
