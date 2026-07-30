"""OPS-71 срез-2: Celery-задача асинхронного импорта (разд. 71.1, «Прогресс»).

Задача — тонкая обёртка: вся логика в ``modules/imports/runner.py``, и её можно
позвать без брокера (так её и проверяют тесты). Обёртка отвечает ровно за две
вещи: тенант-контекст и сессию.

Ретраев НЕТ намеренно. Импорт применяет данные порциями и коммитит их по ходу
(иначе не бывает прогресса), поэтому «повторить задачу» означало бы применить
часть строк дважды. Партия, дошедшая до ``failed``, повторно не запускается:
``execute_import_batch`` берёт в работу только ``pending``. Восстановление —
осознанное действие человека: посмотреть отчёт, откатить партию, загрузить файл
заново.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.tenant import tenant_context
from app.db import ensure_tenant_schema, session_scope
from app.models.imports import ImportBatch
from app.models.tenanting import Tenant
from app.modules.imports.runner import execute_import_batch
from app.services.celery_app import celery_app
from app.tasks._shared import _run_coroutine

logger = logging.getLogger(__name__)

__all__ = ["run_import_batch_job"]


@celery_app.task(name="imports.run_batch")
def run_import_batch_job(tenant_slug: str, batch_id: str) -> dict[str, str]:
    async def _run() -> dict[str, str]:
        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            async with session_scope(tenant=tenant_slug) as session:
                tenant = (
                    await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
                ).scalar_one_or_none()
                if tenant is None:
                    return {"status": "tenant_missing", "batch_id": batch_id}
                batch = await session.get(ImportBatch, batch_id)
                if batch is None or batch.tenant_id != str(tenant.id):
                    # Партия чужая или удалена — молча выходим: делать вид, что
                    # импортировали, нельзя, а ронять воркер незачем.
                    return {"status": "batch_missing", "batch_id": batch_id}
                result = await execute_import_batch(session, tenant, batch)
                return {"status": result.status, "batch_id": batch_id}

    return _run_coroutine(_run())
