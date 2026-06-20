"""
POST /telemetry
- Validates payload
- Stores telemetry (idempotent on device_id + timestamp)
- Updates device_latest
- Runs alert checks and persists them
- Broadcasts to WebSocket clients
"""
import logging
from datetime import timezone

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status

from alerting import evaluate_alerts
from database import get_db
from schemas import AlertRecord, TelemetryPayload, TelemetryResponse
from ws_manager import manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/telemetry",
    response_model=TelemetryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_telemetry(
    payload: TelemetryPayload,
    db: aiosqlite.Connection = Depends(get_db),
):
    # Normalise timestamp to UTC ISO string
    ts = payload.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts_str = ts.isoformat()

    # -------------------------------------------------------------------
    # 1. Insert telemetry (UNIQUE constraint handles duplicates gracefully)
    # -------------------------------------------------------------------
    try:
        cursor = await db.execute(
            """
            INSERT INTO telemetry
                (device_id, timestamp, temperature, energy, voltage, current, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id, timestamp) DO NOTHING
            RETURNING id
            """,
            (
                payload.deviceId,
                ts_str,
                payload.temperature,
                payload.energyConsumption,
                payload.voltage,
                payload.current,
                payload.status,
            ),
        )
        row = await cursor.fetchone()
    except Exception as exc:
        logger.exception("DB insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Database error during telemetry insert")

    if row is None:
        # Duplicate — idempotent: return 200 OK with a note
        cursor2 = await db.execute(
            "SELECT id FROM telemetry WHERE device_id=? AND timestamp=?",
            (payload.deviceId, ts_str),
        )
        existing = await cursor2.fetchone()
        telemetry_id = existing["id"] if existing else 0
        await db.commit()
        return TelemetryResponse(
            success=True,
            telemetry_id=telemetry_id,
            alerts_triggered=[],
            message="Duplicate telemetry — already processed",
        )

    telemetry_id = row["id"]

    # -------------------------------------------------------------------
    # 2. Upsert device_latest
    # -------------------------------------------------------------------
    await db.execute(
        """
        INSERT INTO device_latest (device_id, telemetry_id, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(device_id) DO UPDATE SET
            telemetry_id = excluded.telemetry_id,
            updated_at   = excluded.updated_at
        """,
        (payload.deviceId, telemetry_id),
    )

    # -------------------------------------------------------------------
    # 3. Alert evaluation & persistence
    # -------------------------------------------------------------------
    triggered_raw = evaluate_alerts(payload)
    alert_records: list[AlertRecord] = []

    for alert in triggered_raw:
        cursor_a = await db.execute(
            """
            INSERT INTO alerts (device_id, alert_type, message, severity, telemetry_id)
            VALUES (?, ?, ?, ?, ?)
            RETURNING id, created_at
            """,
            (
                payload.deviceId,
                alert["alert_type"],
                alert["message"],
                alert["severity"],
                telemetry_id,
            ),
        )
        a_row = await cursor_a.fetchone()
        alert_records.append(
            AlertRecord(
                id=a_row["id"],
                device_id=payload.deviceId,
                alert_type=alert["alert_type"],
                message=alert["message"],
                severity=alert["severity"],
                telemetry_id=telemetry_id,
                created_at=a_row["created_at"],
            )
        )

    await db.commit()

    # -------------------------------------------------------------------
    # 4. WebSocket broadcast
    # -------------------------------------------------------------------
    broadcast_payload = {
        "type": "telemetry",
        "data": {
            "deviceId": payload.deviceId,
            "timestamp": ts_str,
            "temperature": payload.temperature,
            "energyConsumption": payload.energyConsumption,
            "voltage": payload.voltage,
            "current": payload.current,
            "status": payload.status,
        },
        "alerts": [a.model_dump() for a in alert_records],
    }
    await manager.broadcast(broadcast_payload)

    logger.info(
        "Ingested telemetry id=%d device=%s alerts=%d ws_clients=%d",
        telemetry_id, payload.deviceId, len(alert_records), manager.connection_count,
    )

    return TelemetryResponse(
        success=True,
        telemetry_id=telemetry_id,
        alerts_triggered=alert_records,
    )
