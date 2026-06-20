"""
GET /alerts  — paginated, filterable alert log
"""
import logging
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, Query

from database import get_db
from schemas import AlertRecord

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/alerts", response_model=list[AlertRecord])
async def list_alerts(
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: aiosqlite.Connection = Depends(get_db),
):
    conditions = []
    params: list = []

    if device_id:
        conditions.append("device_id = ?")
        params.append(device_id)
    if severity:
        conditions.append("severity = ?")
        params.append(severity)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params += [limit, offset]

    rows = await db.execute_fetchall(
        f"""
        SELECT id, device_id, alert_type, message, severity, telemetry_id, created_at
        FROM alerts
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        params,
    )

    return [
        AlertRecord(
            id=r["id"],
            device_id=r["device_id"],
            alert_type=r["alert_type"],
            message=r["message"],
            severity=r["severity"],
            telemetry_id=r["telemetry_id"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
