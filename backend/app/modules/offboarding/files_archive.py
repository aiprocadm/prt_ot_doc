"""OPS-72 срез-4 (разд. 72.2): файлы арендатора архивом.

ТЗ: «Полный экспорт данных арендатора: все сущности клиента … в машиночитаемом
виде (JSON/XLSX) **+ файлы (PDF/DOCX) архивом**». Срез-1 отдал только префикс
хранилища и осознанно оставил это на потом: синхронная выгрузка гигабайтов
обрушила бы запрос. Здесь появляется сама выгрузка — с потолками, потому что
проблема гигабайтов никуда не делась.

Решения:

* **Состав архива берётся из тех же колонок, что и удаление** (``file_keys.py``).
  Разойдись эти два списка — клиент получил бы в архиве меньше, чем у него
  стёрли, и обнаружил бы это уже у нового поставщика.
* **Потолки обязательны, и усечение видно ВНУТРИ архива.** ``MANIFEST.json``
  лежит первым файлом и перечисляет: что вошло, что не вошло и почему
  (потолок числа файлов, потолок объёма, объект недоступен). Молча обрезанный
  архив хуже отказа — он выглядит как успех.
* **Недоступный объект не роняет выгрузку.** Один битый ключ в хранилище не
  должен лишать клиента остальных файлов; он попадает в манифест как
  ``unreadable``.
* **Архив собирается в памяти под потолком объёма.** Потолок и есть защита:
  без него «полный экспорт» первого крупного арендатора положил бы процесс.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.offboarding.file_keys import collect_file_keys

__all__ = [
    "TenantFilesArchiveService",
    "ArchiveReport",
    "DEFAULT_MAX_FILES",
    "DEFAULT_MAX_BYTES",
    "ARCHIVE_MANIFEST_NAME",
]

# Потолки одной выгрузки. Числа консервативные намеренно: архив собирается
# синхронно, и «слишком большой» должен упереться в манифест, а не в память.
DEFAULT_MAX_FILES = 5_000
DEFAULT_MAX_BYTES = 512 * 1024 * 1024  # 512 МиБ

ARCHIVE_MANIFEST_NAME = "MANIFEST.json"


@dataclass
class ArchiveReport:
    """Что вошло в архив и что не вошло — с причиной у каждого пропуска."""

    tenant_id: str
    tenant_slug: str
    generated_at: datetime
    included: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    total_keys: int = 0
    total_bytes: int = 0

    @property
    def truncated(self) -> bool:
        return bool(self.skipped)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "tenant_slug": self.tenant_slug,
            "generated_at": self.generated_at.isoformat(),
            "total_keys": self.total_keys,
            "included_files": len(self.included),
            "total_bytes": self.total_bytes,
            "truncated": self.truncated,
            "included": self.included,
            "skipped": self.skipped,
        }


class TenantFilesArchiveService:
    """Собрать файлы арендатора в ZIP (разд. 72.2)."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        tenant_slug: str,
        storage: Any | None = None,
        max_files: int = DEFAULT_MAX_FILES,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self.session = session
        self.tenant_id = str(tenant_id)
        self.tenant_slug = tenant_slug
        self._storage = storage
        self.max_files = max_files
        self.max_bytes = max_bytes

    def _storage_service(self) -> Any:
        if self._storage is None:
            from app.services.file_storage import FileStorageService

            self._storage = FileStorageService.default()
        return self._storage

    async def keys(self) -> list[str]:
        from app.core.rls_policy import RLS_ENABLED_TABLES

        return await collect_file_keys(self.session, RLS_ENABLED_TABLES, tenant_id=self.tenant_id)

    async def build(self) -> tuple[bytes, ArchiveReport]:
        """Собрать архив и отчёт о нём. Отчёт лежит и внутри архива."""

        keys = await self.keys()
        storage = self._storage_service()
        report = ArchiveReport(
            tenant_id=self.tenant_id,
            tenant_slug=self.tenant_slug,
            generated_at=datetime.now(tz=timezone.utc),
            total_keys=len(keys),
        )

        payloads: list[tuple[str, bytes]] = []
        for key in keys:
            if len(payloads) >= self.max_files:
                report.skipped.append({"key": key, "reason": "max_files"})
                continue
            try:
                data = storage.get(key)
            except Exception:  # noqa: BLE001 - один битый ключ не лишает остальных файлов
                report.skipped.append({"key": key, "reason": "unreadable"})
                continue
            if report.total_bytes + len(data) > self.max_bytes:
                report.skipped.append({"key": key, "reason": "max_bytes"})
                continue
            report.total_bytes += len(data)
            payloads.append((key, data))
            report.included.append({"key": key, "bytes": len(data)})

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            # Манифест пишется первым: открывший архив должен увидеть состав и
            # факт усечения раньше, чем начнёт разбирать файлы.
            archive.writestr(
                ARCHIVE_MANIFEST_NAME,
                json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            )
            for key, data in payloads:
                # Ключ хранилища сохраняется как путь внутри архива: по нему
                # файл сопоставляется со строкой из JSON-дампа.
                archive.writestr(f"files/{key}", data)

        return buffer.getvalue(), report
