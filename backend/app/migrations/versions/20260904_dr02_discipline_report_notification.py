"""dr02: тип уведомления «отчёт о состоянии по дисциплинам» (разд. 57.4).

Отчёт среза-50 лежит в базе и ждёт, пока директор сам зайдёт на дашборд —
это архив, а не «авто-отчёт для клиента». Доставка идёт штатными
уведомлениями, а их тип — нативный enum PostgreSQL: без нового label
``DisciplineReport`` вставка упадёт на первом же тике.

``NotificationType`` маппится на ДВА PG-типа (``notifications.type`` →
``notificationtype``, ``notification_templates.type`` →
``notificationtemplatetype``); страж паритета требует label в обоих
(прецедент — re01 с ``AutomationRule``).

Расширение идёт в ``autocommit_block``: PostgreSQL запрещает использовать
новое значение в той же транзакции, где оно добавлено. ``IF NOT EXISTS``
делает шаг retry-safe. SQLite нативных enum не знает — DDL не нужен.

ОТКАТ ОДНОСТОРОННИЙ: PostgreSQL не умеет удалять значение из enum без
пересоздания типа, ``downgrade`` label не трогает — как все прежние
расширения перечислений в этом репозитории (wa03, re01, cd04).

Revision ID: 20260904_dr02_discipline_report_notification
Revises: 20260904_dr01_discipline_status_report
Create Date: 2026-09-04
"""

from __future__ import annotations

from alembic import op

revision = "20260904_dr02_discipline_report_notification"
down_revision = "20260904_dr01_discipline_status_report"
branch_labels = None
depends_on = None

_LABEL = "DisciplineReport"
_ENUM_TYPES = ("notificationtype", "notificationtemplatetype")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        for enum_type in _ENUM_TYPES:
            op.execute(f"ALTER TYPE {enum_type} ADD VALUE IF NOT EXISTS '{_LABEL}'")


def downgrade() -> None:
    # Label не удаляется: PostgreSQL не умеет DROP VALUE у enum без
    # пересоздания типа. Односторонний шаг, как wa03/re01/cd04.
    pass
