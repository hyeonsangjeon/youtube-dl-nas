"""WebSocket endpoint for real-time download status updates."""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.download import Download
from app.services.download_manager import download_manager
from app.ws.manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Handle WebSocket connections for real-time status updates."""
    await ws_manager.connect(websocket)

    # Auto-push current state on connect
    await _send_state(websocket)
    await _send_history(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                continue

            msg_type = message.get("type")

            if msg_type == "request_state":
                await _send_state(websocket)

            elif msg_type == "request_history":
                await _send_history(websocket)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket error: %s", e)
    finally:
        await ws_manager.disconnect(websocket)


async def _send_state(websocket: WebSocket) -> None:
    """Send current download state to a single client."""
    state = {
        "type": "state",
        "data": {
            "is_downloading": download_manager.current_download_id is not None,
            "current_download_id": download_manager.current_download_id,
            "queue_size": download_manager.queue_size,
            "connected_clients": ws_manager.client_count,
        },
    }
    await ws_manager.send_personal(websocket, state)


async def _send_history(websocket: WebSocket) -> None:
    """Send download history to a single client."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Download).order_by(Download.created_at.desc()).limit(100)
        )
        items = result.scalars().all()
        for item in items:
            await ws_manager.send_personal(websocket, {
                "type": "history_item",
                "data": {
                    "id": item.id,
                    "url": item.url,
                    "title": item.title,
                    "channel": item.channel,
                    "thumbnail_url": item.thumbnail_url,
                    "resolution": item.resolution,
                    "status": item.status,
                    "progress": item.progress,
                    "filename": item.filename,
                    "filepath": item.filepath,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "completed_at": item.completed_at.isoformat() if item.completed_at else None,
                },
            })
        await ws_manager.send_personal(websocket, {
            "type": "history_complete",
            "data": {"total": len(items)},
        })
