"""WebSocket connection manager for real-time broadcast."""

import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket client connections and broadcasting."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a WebSocket connection and register the client."""
        await websocket.accept()
        self._clients.add(websocket)
        logger.info("WebSocket connected. Total: %d", len(self._clients))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a WebSocket client."""
        self._clients.discard(websocket)
        logger.info("WebSocket disconnected. Total: %d", len(self._clients))

    async def broadcast(self, message: dict) -> None:
        """Send a JSON message to all connected clients."""
        disconnected: set[WebSocket] = set()
        for client in self._clients:
            try:
                await client.send_json(message)
            except Exception:
                disconnected.add(client)
        for client in disconnected:
            self._clients.discard(client)

    async def send_personal(self, websocket: WebSocket, message: dict) -> None:
        """Send a JSON message to a specific client."""
        try:
            await websocket.send_json(message)
        except Exception:
            self._clients.discard(websocket)

    @property
    def client_count(self) -> int:
        """Return the number of connected clients."""
        return len(self._clients)


ws_manager = ConnectionManager()
