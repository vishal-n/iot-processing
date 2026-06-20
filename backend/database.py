"""
Database layer using SQLite (aiosqlite) for local dev.
In production, swap for PostgreSQL with asyncpg.
"""
import logging
import os
from pathlib import Path

import aiosqlite

_default_db = Path(__file__).parent / "telemetry.db"
DB_PATH = Path(os.getenv("DB_PATH", str(_default_db)))
logger = logging.getLogger(__name__)


async def get_db() -> aiosqlite.Connection:
    """Dependency: yields an aiosqlite connection with row_factory set."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db():
    """Create tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id     TEXT    NOT NULL,
                timestamp     TEXT    NOT NULL,
                temperature   REAL    NOT NULL,
                energy        REAL    NOT NULL,
                voltage       REAL    NOT NULL,
                current       REAL    NOT NULL,
                status        TEXT    NOT NULL,
                received_at   TEXT    NOT NULL DEFAULT (datetime('now')),
                UNIQUE(device_id, timestamp)          -- idempotency key
            );

            CREATE INDEX IF NOT EXISTS idx_telemetry_device
                ON telemetry(device_id, timestamp DESC);

            CREATE TABLE IF NOT EXISTS device_latest (
                device_id     TEXT PRIMARY KEY,
                telemetry_id  INTEGER REFERENCES telemetry(id),
                updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id     TEXT    NOT NULL,
                alert_type    TEXT    NOT NULL,
                message       TEXT    NOT NULL,
                severity      TEXT    NOT NULL DEFAULT 'warning',
                telemetry_id  INTEGER REFERENCES telemetry(id),
                created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_alerts_device
                ON alerts(device_id, created_at DESC);
        """)
        await db.commit()
        logger.info("DB schema ready at %s", DB_PATH)
