"""
IoT Telemetry Backend - FastAPI
Entry point for the application.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import telemetry, devices, alerts, websocket

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting IoT Telemetry Service...")
    await init_db()
    logger.info("Database initialized.")
    yield
    logger.info("Shutting down IoT Telemetry Service.")


app = FastAPI(
    title="IoT Telemetry API",
    description="Production-grade IoT telemetry ingestion, alerting, and WebSocket broadcasting.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(telemetry.router, tags=["Telemetry"])
app.include_router(devices.router, tags=["Devices"])
app.include_router(alerts.router, tags=["Alerts"])
app.include_router(websocket.router, tags=["WebSocket"])


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "iot-telemetry"}
