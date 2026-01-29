"""WebSocket stub endpoints (P2 deferred)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.get("/ws/v1/events")
async def ws_events_stub() -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="WebSocket events are deferred to P2. Use REST endpoints for now.",
    )
