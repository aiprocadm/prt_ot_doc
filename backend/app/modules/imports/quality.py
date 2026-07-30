"""OPS-71 срез-7 (разд. 71.3): проверки Data Quality по итогам импорта.

ТЗ: «Импортированные данные сразу проходят проверки Data Quality; проблемные —
помечаются, а не тихо принимаются». Движок проверок в проекте уже есть
(``modules/data_quality``) — здесь он наводится на записи КОНКРЕТНОЙ партии.

**Сужение по партии обязательно.** Движок считает по всему арендатору, и без
фильтра пользователь увидел бы в отчёте о своей загрузке чужие давние проблемы —
отчёт, в котором нельзя отличить «я это привёз» от «это было до меня», не
починит никто.

**Проверка не может провалить импорт.** Данные уже записаны; если движок упал,
это повод показать «проверка не выполнилась», а не откатывать загрузку и не
отдавать 500 на успешную операцию.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.imports import ImportBatch, ImportRow
from app.modules.data_quality.service import DataQualityService

__all__ = ["MAX_QUALITY_SAMPLE", "run_quality_check_for_batch"]

logger = logging.getLogger(__name__)

# Сколько проблем класть в партию списком. Полный перечень живёт в отчёте
# Data Quality; здесь нужен повод открыть его, а не второй такой же отчёт.
MAX_QUALITY_SAMPLE = 20


async def _touched_entity_ids(session: AsyncSession, batch: ImportBatch) -> set[str]:
    rows = (
        await session.execute(
            select(ImportRow.entity_id).where(
                ImportRow.tenant_id == batch.tenant_id,
                ImportRow.batch_id == batch.id,
                ImportRow.entity_id.is_not(None),
            )
        )
    ).all()
    return {row[0] for row in rows if row[0]}


async def run_quality_check_for_batch(session: AsyncSession, batch: ImportBatch) -> dict[str, Any]:
    """Прогнать проверки качества и записать итог в ``batch.notes['data_quality']``.

    Возвращает тот же итог. Исключения наружу не выпускаются: импорт уже
    состоялся, и его успех не должен зависеть от вспомогательной проверки.
    """

    touched = await _touched_entity_ids(session, batch)
    if not touched:
        summary: dict[str, Any] = {"issues_total": 0, "by_severity": {}, "sample": []}
        batch.notes = {**(batch.notes or {}), "data_quality": summary}
        return summary

    try:
        report = await DataQualityService(str(batch.tenant_id), session).run_comprehensive_check()
        mine = [issue for issue in report.issues if str(issue.affected_entity_id) in touched]
        by_severity: dict[str, int] = {}
        for issue in mine:
            key = getattr(issue.severity, "value", str(issue.severity))
            by_severity[key] = by_severity.get(key, 0) + 1
        summary = {
            "issues_total": len(mine),
            "by_severity": by_severity,
            "sample": [
                {
                    "severity": getattr(i.severity, "value", str(i.severity)),
                    "title": i.title,
                    "entity_type": i.affected_entity_type,
                    "entity_id": str(i.affected_entity_id),
                    "entity_name": i.affected_entity_name,
                }
                for i in mine[:MAX_QUALITY_SAMPLE]
            ],
            # Усечение видно: «показано 20» без пометки читается как «проблем 20».
            "sample_truncated": len(mine) > MAX_QUALITY_SAMPLE,
        }
    except Exception as exc:  # noqa: BLE001 — движок правил трогает половину схемы
        logger.exception("imports.quality_check_failed", extra={"batch_id": batch.id})
        summary = {"error": str(exc)[:300]}

    batch.notes = {**(batch.notes or {}), "data_quality": summary}
    return summary
