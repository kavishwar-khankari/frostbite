import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

# All currently connected WebSocket clients.
_connections: set[WebSocket] = set()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    _connections.add(websocket)
    logger.info("WebSocket client connected (total: %d)", len(_connections))
    try:
        while True:
            # Keep alive — clients can send pings; we just discard them.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _connections.discard(websocket)
        logger.info("WebSocket client disconnected (total: %d)", len(_connections))


async def broadcast(message: dict[str, Any]) -> None:
    """Broadcast a JSON message to all connected dashboard clients."""
    if not _connections:
        return
    data = json.dumps(message)
    dead: set[WebSocket] = set()
    for ws in list(_connections):
        try:
            await ws.send_text(data)
        except Exception:
            dead.add(ws)
    _connections.difference_update(dead)
