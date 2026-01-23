from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import Outbox

logger = logging.getLogger(__name__)


class OutboxProcessor:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()

    async def run(self) -> None:
        while True:
            await self.process_once()
            await asyncio.sleep(self.settings.outbox_poll_interval)

    async def process_once(self) -> int:
        stmt = select(Outbox).where(Outbox.processed_at.is_(None)).limit(100)
        result = await self.session.execute(stmt)
        entries = result.scalars().all()
        processed = 0
        for entry in entries:
            logger.info("outbox.dispatch", extra={"event_type": entry.event_type})
            entry.processed_at = datetime.utcnow()
            processed += 1
        if processed:
            await self.session.commit()
        return processed
