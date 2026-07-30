"""OPS-71 (разд. 71.1): партия импорта и её строки.

Партия существует ради двух требований ТЗ, которые без неё невыполнимы:
**«Откат импорта — отменить импортированную партию целиком (по import batch id)»**
и **«Отчёт об импорте … с привязкой к batch id»**.

Ключевое: у строки обновления хранится снимок ПРЕЖНИХ значений изменённых полей.
Без него «откатить партию» — обещание, которое нечем исполнить: удалить созданное
можно и так, а вернуть перезаписанное неоткуда. Снимок узкий (только изменённые
поля), поэтому откат не затирает правки, сделанные людьми в других полях.

Сухой прогон (dry-run) здесь НЕ появляется: разд. 71.1 требует показать результат
«БЕЗ записи в БД», а партия — это запись. Предпросмотр возвращается ответом.

Обе таблицы tenant-scoped и армируются RLS (SEC-65) той же миграцией.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import TenantBaseModel

__all__ = [
    "IMPORT_BATCH_STATUSES",
    "IMPORT_ROW_ACTIONS",
    "IMPORT_TERMINAL_STATUSES",
    "ImportBatch",
    "ImportRow",
]

IMPORT_BATCH_STATUSES: tuple[str, ...] = (
    # Файл принят и поставлен в очередь, обработка ещё не началась (async).
    "pending",
    # Обработка идёт: ``processed_rows`` растёт, по нему рисуется прогресс.
    "running",
    # Партия применена: часть строк создана/обновлена, ошибочные отложены.
    "applied",
    # Обработка оборвалась целиком (нечитаемый файл, упавший воркер).
    # Строки, применённые до обрыва, остаются и откатываются штатным откатом —
    # именно поэтому статус отдельный, а не «как будто ничего не было».
    "failed",
    # Партия отменена целиком.
    "rolled_back",
)

# Статусы, из которых партия уже не сдвинется сама.
IMPORT_TERMINAL_STATUSES: frozenset[str] = frozenset({"applied", "failed", "rolled_back"})

IMPORT_ROW_ACTIONS: tuple[str, ...] = ("created", "updated", "skipped", "failed")


class ImportBatch(TenantBaseModel):
    """Одна применённая загрузка файла."""

    __tablename__ = "import_batch"
    __table_args__ = (
        Index("ix_import_batch_tenant_target", "tenant_id", "target"),
        Index("ix_import_batch_tenant_status", "tenant_id", "status"),
    )

    target: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="applied")

    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_format: Mapped[str] = mapped_column(String(16), nullable=False)

    # Схема маппинга «поле модели → заголовок файла». Разд. 71.1 требует
    # «сохранение схемы маппинга для повтора»: следующая загрузка того же
    # выгружаемого отчёта берёт схему отсюда, а не собирается заново руками.
    mapping: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Заголовки без пары и неизвестные значения справочников — то, что человек
    # должен увидеть, чтобы починить источник, а не гадать по числам.
    notes: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    # Сколько строк уже обработано. Растёт по ходу асинхронного импорта и
    # коммитится отдельной транзакцией: прогресс, видимый только в конце, —
    # это не прогресс, адва состояния «ничего» и «всё».
    processed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Ключ исходного файла в хранилище. Воркер живёт в другом процессе, и тело
    # запроса ему недоступно — файл кладётся в хранилище арендатора, а после
    # терминального статуса удаляется: это ПДн, и держать вторую копию дольше
    # необходимого незачем (SEC-66).
    source_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Причина обрыва. Пустой ``failed`` без причины заставляет лезть в логи.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    applied_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Момент постановки партии: для синхронного импорта он же и момент записи,
    # для асинхронного — время приёма файла. Завершение — ``finished_at``.
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rolled_back_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ImportRow(TenantBaseModel):
    """Судьба одной строки файла в рамках партии."""

    __tablename__ = "import_row"
    __table_args__ = (Index("ix_import_row_batch_action", "batch_id", "action"),)

    batch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("import_batch.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)

    # Ключ, по которому строка считается «той же самой» при повторной загрузке.
    natural_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Таблица и id затронутой записи. Внешнего ключа нет намеренно: цель импорта
    # полиморфна (сотрудники, должности, дальше — что угодно), а FK на «любую
    # таблицу» не бывает. Откат ищет запись по этой паре.
    entity_table: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Снимок прежних значений ИЗМЕНЁННЫХ полей — топливо отката.
    before_values: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    errors: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
