"""
GET /devices/:deviceId/latest
GET /devices/:deviceId/summary
"""
import logging

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from database import get_db
from schemas import DeviceSummary, TelemetryRecord

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/devices/{device_id}/latest", response_model=TelemetryRecord)
async def get_latest(device_id: str, db: aiosqlite.Connection = Depends(get_db)):
    row = await db.execute_fetchall(
        """
        SELECT t.*
        FROM telemetry t
        JOIN device_latest dl ON dl.telemetry_id = t.id
        WHERE dl.device_id = ?
        """,
        (device_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    r = row[0]
    return TelemetryRecord(
        id=r["id"],
        device_id=r["device_id"],
        timestamp=r["timestamp"],
        temperature=r["temperature"],
        energy=r["energy"],
        voltage=r["voltage"],
        current=r["current"],
        status=r["status"],
        received_at=r["received_at"],
    )


@router.get("/devices/{device_id}/summary", response_model=DeviceSummary)
async def get_summary(device_id: str, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall(
        """
        SELECT
            COUNT(*)           AS total_readings,
            AVG(temperature)   AS avg_temperature,
            AVG(energy)        AS avg_energy,
            AVG(voltage)       AS avg_voltage,
            AVG(current)       AS avg_current,
            MAX(timestamp)     AS last_seen
        FROM telemetry
        WHERE device_id = ?
        """,
        (device_id,),
    )
    if not rows or rows[0]["total_readings"] == 0:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")

    # Latest status
    status_rows = await db.execute_fetchall(
        """
        SELECT t.status
        FROM telemetry t
        JOIN device_latest dl ON dl.telemetry_id = t.id
        WHERE dl.device_id = ?
        """,
        (device_id,),
    )
    latest_status = status_rows[0]["status"] if status_rows else None

    r = rows[0]
    return DeviceSummary(
        device_id=device_id,
        total_readings=r["total_readings"],
        avg_temperature=round(r["avg_temperature"], 2) if r["avg_temperature"] else None,
        avg_energy=round(r["avg_energy"], 2) if r["avg_energy"] else None,
        avg_voltage=round(r["avg_voltage"], 2) if r["avg_voltage"] else None,
        avg_current=round(r["avg_current"], 2) if r["avg_current"] else None,
        last_seen=r["last_seen"],
        status=latest_status,
    )
