"""
WebSocket connection manager.
Tracks all connected clients and broadcasts JSON messages to them.
"""
import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        logger.info("WS client connected. Total: %d", len(self._connections))

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._connections.discard(ws)
        logger.info("WS client disconnected. Total: %d", len(self._connections))

    async def broadcast(self, data: dict[str, Any]):
        """Send JSON payload to every connected client; remove dead connections."""
        message = json.dumps(data, default=str)
        dead: set[WebSocket] = set()

        async with self._lock:
            connections = set(self._connections)

        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)

        if dead:
            async with self._lock:
                self._connections -= dead
            logger.info("Removed %d dead WS connections.", len(dead))

    @property
    def connection_count(self) -> int:
        return len(self._connections)


# Singleton shared across the app
manager = ConnectionManager()
