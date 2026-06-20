"""
WebSocket endpoint: ws://localhost:8000/ws/telemetry
"""
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ws_manager import manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/telemetry")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        # Send a handshake greeting
        await ws.send_json({"type": "connected", "message": "IoT Telemetry WebSocket ready"})
        # Keep connection alive; we only push, but we still need to listen for
        # client-side close or ping frames.
        while True:
            # receive_text() will raise WebSocketDisconnect on client close
            await ws.receive_text()
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected normally.")
    except Exception as exc:
        logger.warning("WebSocket error: %s", exc)
    finally:
        await manager.disconnect(ws)
