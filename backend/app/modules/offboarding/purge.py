"""OPS-72 срез-3 (разд. 72.3): исполнение удаления данных арендатора.

Срез-2 остановился на плане: «удаление в обратном порядке зависимостей» падает
на циклах внешних ключей, а необратимая операция в обход этого факта стирала бы
данные ЧАСТИЧНО И МОЛЧА. Здесь цикл разрывается явно — обнулением необязательных
ссылок (``schema_graph.py``), а разорванные связи попадают в акт.

Правила, которые важнее кода:

* **Исполняется утверждённый план, а не «что получится».** План строит
  ``lifecycle.build_purge_plan``; исполнение берёт из него тот же список
  удерживаемых таблиц. Разойтись они не могут — оба зовут ``retained_tables``.
* **Удаление не начинается, пока grace не истёк.** Это единственная защита
  клиента, который передумал; обходить её «флагом force» нельзя — короткий
  grace задаётся при заявке (``grace_days=0``), и это видно в записи.
* **Файлы удаляются по ключам из строк, а не по префиксу хранилища.** Ключи
  собираются ДО удаления строк: после него узнать, что именно принадлежало
  арендатору, уже неоткуда. Префикс же — догадка о раскладке бакета, и на первой
  же нестандартной раскладке она либо не удалит чужого, либо удалит лишнее.
* **Акт переживает удаление.** ``tenant_offboarding`` и запись акта в ней
  сохраняются: вопрос «что именно вы стёрли и когда» задают ровно тогда, когда
  самих данных уже нет.
* **Обезличивание — по явному списку колонок.** Эвристика «имя колонки похоже на
  ПДн» на необратимой операции недопустима: пропущенная колонка означает, что
  ПДн остались в базе, которую клиент считает вычищенной. Полноту списка стережёт
  тест, который сам ищет идентификаторы в удерживаемых таблицах.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.sql_text import quote_identifier
from app.modules.offboarding import backup_retention
from app.modules.offboarding.file_keys import collect_file_keys
from app.modules.offboarding.lifecycle import (
    OffboardingStateError,
    TenantOffboardingService,
)
from app.modules.offboarding.schema_graph import ForeignLink

__all__ = [
    "TenantPurgeService",
    "PurgeAct",
    "ANONYMIZED_COLUMNS",
    "PURGE_SURVIVING_TABLES",
]

# Таблицы, которые переживают удаление. Их ровно одна: сам офбординг с актом.
# Всё остальное — данные арендатора, и «мы удалили, но кое-что оставили себе»
# — это не удаление.
PURGE_SURVIVING_TABLES: frozenset[str] = frozenset({"tenant_offboarding"})

# Чем заменяются прямые идентификаторы при обезличивании.
#
# Список ЯВНЫЙ: обезличивание необратимо, и пропущенная колонка означает ПДн,
# оставшиеся в базе, которую клиент считает вычищенной. Значения — выражения SQL,
# работающие и в PostgreSQL, и в SQLite (тесты гоняются на обоих).
#
# ``person`` — единственная таблица с прямыми идентификаторами субъекта; список
# полей совпадает с ``SCRUBBED_PERSON_FIELDS`` (SEC-66 срез-2), и это совпадение
# проверяется тестом: два разных обезличивания одного и того же человека —
# гарантированный источник расхождений.
#
# Псевдоним содержит кусок ``id``: строки должны остаться РАЗЛИЧИМЫМИ, иначе
# «сохранить статистику без ПДн» (разд. 72.3) не выполняется.
ANONYMIZED_COLUMNS: dict[str, dict[str, str]] = {
    "person": {
        "first_name": "'Обезличено'",
        "last_name": "'subject-' || substr(id, 1, 8)",
        "middle_name": "NULL",
        "birth_date": "NULL",
        "email": "NULL",
        "phone": "NULL",
        "personnel_number": "NULL",
        "snils": "NULL",
        "passport": "NULL",
        "hired_at": "NULL",
        "qualifications": "'[]'",
        "current_ppe": "'[]'",
        "ppe_sizes": "NULL",
        "position_title": "NULL",
        "anonymized_at": ":now",
    },
    # Свободный текст с ФИО пострадавшего/свидетеля: person_id может быть пуст
    # (внешний человек), и тогда идентификатор лежит именно здесь.
    "incident_persons": {"fio_text": "NULL"},
}


@dataclass
class PurgeAct:
    """Акт: что удалено, что обезличено, что разорвано и когда."""

    tenant_id: str
    tenant_slug: str
    executed_at: datetime
    deleted_rows: dict[str, int] = field(default_factory=dict)
    anonymized_rows: dict[str, int] = field(default_factory=dict)
    retained_tables: dict[str, str] = field(default_factory=dict)
    broken_links: list[str] = field(default_factory=list)
    files_deleted: int = 0
    files_failed: list[str] = field(default_factory=list)
    # OPS-72 (срез-188): удаление из живой базы не равно удалению из резервных
    # копий. Выборочно вычистить строку из копии невозможно, не сделав копию
    # непригодной для восстановления, — поэтому здесь не удаление, а
    # ОБЯЗАТЕЛЬСТВО с вычислимой датой: день удаления плюс срок хранения копий.
    backup_purge: dict[str, Any] = field(default_factory=dict)

    @property
    def rows_deleted(self) -> int:
        return sum(self.deleted_rows.values())

    @property
    def rows_anonymized(self) -> int:
        return sum(self.anonymized_rows.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "tenant_slug": self.tenant_slug,
            "executed_at": self.executed_at.isoformat(),
            "rows_deleted": self.rows_deleted,
            "rows_anonymized": self.rows_anonymized,
            "deleted_rows": self.deleted_rows,
            "anonymized_rows": self.anonymized_rows,
            "retained_tables": self.retained_tables,
            "broken_links": self.broken_links,
            "files_deleted": self.files_deleted,
            "files_failed": self.files_failed,
            "backup_purge": self.backup_purge,
        }


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class TenantPurgeService:
    """Окончательное удаление данных арендатора с актом (разд. 72.3)."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        tenant_slug: str,
        storage: Any | None = None,
    ) -> None:
        self.session = session
        self.tenant_id = str(tenant_id)
        self.tenant_slug = tenant_slug
        self._storage = storage
        self.lifecycle = TenantOffboardingService(
            session, tenant_id=tenant_id, tenant_slug=tenant_slug
        )

    def _storage_service(self) -> Any:
        if self._storage is None:
            from app.services.file_storage import FileStorageService

            self._storage = FileStorageService.default()
        return self._storage

    async def execute(self, *, delete_files: bool = True) -> PurgeAct:
        """Исполнить удаление. Идемпотентно: повторный вызов вернёт тот же акт.

        Порядок операций — не вкусовщина:

        1. ключи файлов собираются, пока строки ещё существуют;
        2. рвутся циклические ссылки (иначе шаг 3 упадёт на середине);
        3. удаляются строки в обратном порядке зависимостей;
        4. обезличиваются удерживаемые таблицы;
        5. удаляются файлы — последними: если упадёт хранилище, база уже
           консистентна, а не наоборот, и незакрытые ключи видны в акте.
        """

        record = await self.lifecycle.current()
        if record is None:
            raise OffboardingStateError("Заявка на офбординг не подана")
        if record.status == "purged":
            act = record.purge_act or {}
            return _act_from_dict(act, tenant_id=self.tenant_id, tenant_slug=self.tenant_slug)
        if record.status != "grace":
            raise OffboardingStateError(f"Недопустимый статус офбординга: {record.status}")

        grace_until = record.grace_until
        if grace_until.tzinfo is None:
            grace_until = grace_until.replace(tzinfo=timezone.utc)
        if grace_until > _utcnow():
            raise OffboardingStateError(
                "Grace-период не истёк: удалять данные рано " f"(до {grace_until.isoformat()})"
            )

        retained = await self.lifecycle.retained_tables()
        graph = await self.lifecycle.schema_graph()
        doomed = [
            table
            for table in graph.tables
            if table not in retained and table not in PURGE_SURVIVING_TABLES
        ]

        act = PurgeAct(
            tenant_id=self.tenant_id,
            tenant_slug=self.tenant_slug,
            executed_at=_utcnow(),
            retained_tables=dict(sorted(retained.items())),
        )
        # Обязательство считается СРАЗУ и попадает в акт: посчитанное потом
        # «когда-нибудь» на практике не считается никогда.
        act.backup_purge = backup_retention.build_obligation(
            purged_at=act.executed_at, settings=get_settings()
        )

        file_keys = await self._collect_file_keys(doomed) if delete_files else []

        order, broken = graph.deletion_order(doomed)
        for link in broken:
            await self._break_link(link)
        act.broken_links = sorted(link.describe() for link in broken)

        for table in order:
            deleted = await self._delete_rows(table)
            if deleted:
                act.deleted_rows[table] = deleted

        for table, columns in ANONYMIZED_COLUMNS.items():
            if table not in retained:
                # Таблица идёт под удаление целиком — обезличивать нечего.
                continue
            updated = await self._anonymize(table, columns)
            if updated:
                act.anonymized_rows[table] = updated

        if delete_files:
            deleted_files, failed = self._delete_files(file_keys)
            act.files_deleted = deleted_files
            act.files_failed = failed

        record.status = "purged"
        record.purged_at = act.executed_at
        record.purge_act = act.to_dict()
        await self.session.flush()
        return act

    async def _break_link(self, link: ForeignLink) -> None:
        """Обнулить необязательную ссылку, чтобы разорвать цикл."""

        # Имена таблиц и колонок сняты с самой базы, а не пришли из запроса.
        # Идентификатор параметром не передать — значит, проверка формата перед
        # склейкой (разд. 64.1, строка «Injection»; дом правила — core/sql_text).
        assignments = ", ".join(
            f"{quote_identifier(column, source='карта связей схемы')} = NULL"
            for column in link.columns
        )
        child = quote_identifier(link.child, source="карта связей схемы")
        await self.session.execute(
            text(f"UPDATE {child} SET {assignments} WHERE tenant_id = :tenant"),
            {"tenant": self.tenant_id},
        )

    async def _delete_rows(self, table: str) -> int:
        quoted = quote_identifier(table, source="карта таблиц схемы")
        result = await self.session.execute(
            text(f"DELETE FROM {quoted} WHERE tenant_id = :tenant"),
            {"tenant": self.tenant_id},
        )
        return int(result.rowcount or 0)

    async def _anonymize(self, table: str, columns: dict[str, str]) -> int:
        assignments = ", ".join(
            f"{quote_identifier(column, source='правила обезличивания')} = {value}"
            for column, value in columns.items()
        )
        quoted = quote_identifier(table, source="правила обезличивания")
        params: dict[str, Any] = {"tenant": self.tenant_id}
        if ":now" in assignments:
            params["now"] = _utcnow()
        result = await self.session.execute(
            text(f"UPDATE {quoted} SET {assignments} WHERE tenant_id = :tenant"),
            params,
        )
        return int(result.rowcount or 0)

    async def _collect_file_keys(self, tables: list[str]) -> list[str]:
        """Ключи файлов арендатора — собираются ДО удаления строк.

        Тот же сборщик, что и у выгрузки архивом (``file_keys.py``): архив и
        удаление обязаны видеть один и тот же набор файлов, иначе клиент
        получит меньше, чем у него стёрли.
        """

        return await collect_file_keys(self.session, tables, tenant_id=self.tenant_id)

    def _delete_files(self, keys: list[str]) -> tuple[int, list[str]]:
        """Удалить файлы. Неудача по ключу не отменяет удаление базы: она
        попадает в акт — «эти объекты остались, разберитесь вручную» честнее,
        чем откат уже удалённых данных."""

        if not keys:
            return 0, []
        storage = self._storage_service()
        deleted = 0
        failed: list[str] = []
        for key in keys:
            try:
                storage.delete(key)
            except Exception:  # noqa: BLE001 - хранилище не должно рушить акт
                failed.append(key)
            else:
                deleted += 1
        return deleted, failed


def _act_from_dict(payload: dict[str, Any], *, tenant_id: str, tenant_slug: str) -> PurgeAct:
    executed_at = payload.get("executed_at")
    return PurgeAct(
        tenant_id=payload.get("tenant_id", tenant_id),
        tenant_slug=payload.get("tenant_slug", tenant_slug),
        executed_at=(
            datetime.fromisoformat(executed_at) if isinstance(executed_at, str) else _utcnow()
        ),
        deleted_rows=dict(payload.get("deleted_rows") or {}),
        anonymized_rows=dict(payload.get("anonymized_rows") or {}),
        retained_tables=dict(payload.get("retained_tables") or {}),
        broken_links=list(payload.get("broken_links") or []),
        files_deleted=int(payload.get("files_deleted") or 0),
        files_failed=list(payload.get("files_failed") or []),
        backup_purge=dict(payload.get("backup_purge") or {}),
    )
