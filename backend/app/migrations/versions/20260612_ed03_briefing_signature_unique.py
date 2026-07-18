"""ed03: unique-индекс против гонки дублей briefing-подписей (ЭДО Срез-1, тех-долг).

Зафиксированная гонка: конкурентные подписания одного briefing_entry одним
signer_type оба проходят existing-check в BriefingEntryService.sign и оба
INSERT'ят — в таблице briefing_signatures появляются дубли пары
(briefing_entry_id, signer_type).

upgrade: СНАЧАЛА дедуп существующих дублей (остаётся самая ранняя запись по
signed_at, tie-break — меньший id; остальные удаляются), ПОТОМ unique-индекс
uq_briefing_signatures_entry_signer. Дедуп диалектно-нейтрален (коррелированный
EXISTS, без PG-специфичных конструкций) — работает на SQLite и PostgreSQL.

downgrade: только дроп индекса. Удалённые при upgrade дубли НЕ
восстанавливаются — это честно: они были артефактом гонки, канонической
записью считается самая ранняя подпись.
"""

from __future__ import annotations

from alembic import op

revision = "20260612_ed03_briefing_signature_unique"
down_revision = "20260612_ed02_drop_legacy_signing_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Дедуп: удалить все записи, для которых существует более ранняя запись
    #    той же пары (briefing_entry_id, signer_type). Сравнение signed_at,
    #    при равенстве — меньший id выживает. Диалектно-нейтрально SQLite/PG.
    op.execute(
        "DELETE FROM briefing_signatures "
        "WHERE EXISTS ("
        "    SELECT 1 FROM briefing_signatures AS earlier"
        "    WHERE earlier.briefing_entry_id = briefing_signatures.briefing_entry_id"
        "      AND earlier.signer_type = briefing_signatures.signer_type"
        "      AND ("
        "          earlier.signed_at < briefing_signatures.signed_at"
        "          OR (earlier.signed_at = briefing_signatures.signed_at"
        "              AND earlier.id < briefing_signatures.id)"
        "      )"
        ")"
    )
    # 2) Unique-индекс: закрывает окно гонки на уровне БД.
    op.create_index(
        "uq_briefing_signatures_entry_signer",
        "briefing_signatures",
        ["briefing_entry_id", "signer_type"],
        unique=True,
    )


def downgrade() -> None:
    # Дубли, удалённые в upgrade, не восстанавливаются (см. docstring).
    op.drop_index("uq_briefing_signatures_entry_signer", table_name="briefing_signatures")
