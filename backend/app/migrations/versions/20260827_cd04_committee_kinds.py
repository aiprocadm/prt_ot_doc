"""cd04: виды комиссий ГО и ЧС — КЧС и ПБ, эвакокомиссия (разд. 56.1).

Требование «Комиссии: КЧС и ПБ, эвакокомиссия — составы, приказы, протоколы,
решения» упиралось В СЛОВАРЬ, а не в новый контур: ``committee`` со составами,
заседаниями, протоколами, решениями и голосами существует с cmt01. Дисциплине
ГО и ЧС не хватало ровно двух значений перечисления ``committeekind``.

Своего реестра комиссий ГО НЕ заводим: это дублировало бы ядро вопреки
принципу мультидисциплинарности (преамбула разд. 54).

Расширение нативного enum идёт в ``autocommit_block``: PostgreSQL запрещает
использовать новое значение в той же транзакции, где оно добавлено
(прецедент — 20260530_wa03_prescription_lifecycle). ``IF NOT EXISTS`` делает
шаг retry-safe. SQLite нативных enum не знает (колонка ведёт себя как TEXT), а
тестовая схема строится из метаданных ORM — DDL для него не нужен.

ОТКАТ ОДНОСТОРОННИЙ: PostgreSQL не умеет удалять значение из enum без
пересоздания типа, поэтому ``downgrade`` НЕ удаляет добавленные значения —
как и все прежние расширения перечислений в этом репозитории.

Revision ID: 20260827_cd04_committee_kinds
Revises: 20260827_sec65_rls_cd_drill
Create Date: 2026-08-27
"""

from __future__ import annotations

from alembic import op

revision = "20260827_cd04_committee_kinds"
down_revision = "20260827_sec65_rls_cd_drill"
branch_labels = None
depends_on = None

_NEW_VALUES = ("commission_emergency", "commission_evacuation")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        for value in _NEW_VALUES:
            op.execute(f"ALTER TYPE committeekind ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # Значения НЕ удаляются: PostgreSQL не умеет DROP VALUE у enum без
    # пересоздания типа. Односторонний шаг, как и прежние расширения
    # перечислений в этом репозитории (прецедент wa03).
    pass
