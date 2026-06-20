"""
Pydantic models for request/response validation.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Inbound
# ---------------------------------------------------------------------------

class TelemetryPayload(BaseModel):
    deviceId: str = Field(..., min_length=1, max_length=64)
    timestamp: datetime
    temperature: float
    energyConsumption: float
    voltage: float
    current: float
    status: str = Field(..., min_length=1, max_length=32)

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v):
        if not (-50 <= v <= 150):
            raise ValueError(f"Temperature {v}°C is outside plausible range [-50, 150]")
        return v

    @field_validator("voltage")
    @classmethod
    def validate_voltage(cls, v):
        if not (0 <= v <= 500):
            raise ValueError(f"Voltage {v}V is outside plausible range [0, 500]")
        return v

    @field_validator("current")
    @classmethod
    def validate_current(cls, v):
        if not (0 <= v <= 100):
            raise ValueError(f"Current {v}A is outside plausible range [0, 100]")
        return v

    @field_validator("energyConsumption")
    @classmethod
    def validate_energy(cls, v):
        if not (0 <= v <= 1000):
            raise ValueError(f"Energy {v}kWh is outside plausible range [0, 1000]")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        allowed = {"online", "offline", "idle", "error", "maintenance"}
        if v.lower() not in allowed:
            raise ValueError(f"Status '{v}' not in allowed set {allowed}")
        return v.lower()


# ---------------------------------------------------------------------------
# Outbound
# ---------------------------------------------------------------------------

class TelemetryRecord(BaseModel):
    id: int
    device_id: str
    timestamp: str
    temperature: float
    energy: float
    voltage: float
    current: float
    status: str
    received_at: str


class AlertRecord(BaseModel):
    id: int
    device_id: str
    alert_type: str
    message: str
    severity: str
    telemetry_id: Optional[int]
    created_at: str


class TelemetryResponse(BaseModel):
    success: bool
    telemetry_id: int
    alerts_triggered: list[AlertRecord]
    message: str = "Telemetry accepted"


class DeviceSummary(BaseModel):
    device_id: str
    total_readings: int
    avg_temperature: Optional[float]
    avg_energy: Optional[float]
    avg_voltage: Optional[float]
    avg_current: Optional[float]
    last_seen: Optional[str]
    status: Optional[str]
