"""
Alerting engine — evaluates rules against each incoming telemetry reading.
Add new rules by appending to RULES list below.
"""
import logging
from dataclasses import dataclass
from typing import Callable

from schemas import TelemetryPayload

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds (could be loaded from config/env in production)
# ---------------------------------------------------------------------------
TEMP_HIGH_THRESHOLD = 40.0          # °C
TEMP_LOW_THRESHOLD = -10.0          # °C
ENERGY_SPIKE_THRESHOLD = 10.0       # kWh — single reading
ENERGY_HIGH_THRESHOLD = 8.0         # kWh
VOLTAGE_LOW = 180.0
VOLTAGE_HIGH = 260.0
CURRENT_HIGH = 15.0


@dataclass
class AlertRule:
    alert_type: str
    severity: str                    # critical | warning | info
    check: Callable[[TelemetryPayload], str | None]
    """Return a message string if the rule fires, else None."""


def _check_high_temp(t: TelemetryPayload) -> str | None:
    if t.temperature > TEMP_HIGH_THRESHOLD:
        return (
            f"Temperature {t.temperature}°C exceeds threshold {TEMP_HIGH_THRESHOLD}°C"
        )
    return None


def _check_low_temp(t: TelemetryPayload) -> str | None:
    if t.temperature < TEMP_LOW_THRESHOLD:
        return (
            f"Temperature {t.temperature}°C is below minimum {TEMP_LOW_THRESHOLD}°C"
        )
    return None


def _check_energy_spike(t: TelemetryPayload) -> str | None:
    if t.energyConsumption > ENERGY_SPIKE_THRESHOLD:
        return (
            f"Energy spike detected: {t.energyConsumption} kWh "
            f"exceeds spike threshold {ENERGY_SPIKE_THRESHOLD} kWh"
        )
    if t.energyConsumption > ENERGY_HIGH_THRESHOLD:
        return (
            f"High energy consumption: {t.energyConsumption} kWh "
            f"exceeds normal threshold {ENERGY_HIGH_THRESHOLD} kWh"
        )
    return None


def _check_device_offline(t: TelemetryPayload) -> str | None:
    if t.status in ("offline", "error"):
        return f"Device {t.deviceId} reported status '{t.status}'"
    return None


def _check_voltage_anomaly(t: TelemetryPayload) -> str | None:
    if t.voltage < VOLTAGE_LOW:
        return f"Low voltage: {t.voltage}V (min {VOLTAGE_LOW}V)"
    if t.voltage > VOLTAGE_HIGH:
        return f"High voltage: {t.voltage}V (max {VOLTAGE_HIGH}V)"
    return None


def _check_current_anomaly(t: TelemetryPayload) -> str | None:
    if t.current > CURRENT_HIGH:
        return f"High current draw: {t.current}A (max {CURRENT_HIGH}A)"
    return None


# All active rules
RULES: list[AlertRule] = [
    AlertRule("HIGH_TEMPERATURE",   "critical", _check_high_temp),
    AlertRule("LOW_TEMPERATURE",    "warning",  _check_low_temp),
    AlertRule("ENERGY_SPIKE",       "critical", _check_energy_spike),
    AlertRule("DEVICE_OFFLINE",     "critical", _check_device_offline),
    AlertRule("VOLTAGE_ANOMALY",    "warning",  _check_voltage_anomaly),
    AlertRule("CURRENT_ANOMALY",    "warning",  _check_current_anomaly),
]


def evaluate_alerts(payload: TelemetryPayload) -> list[dict]:
    """
    Evaluate all rules against the payload.
    Returns a list of dicts ready to INSERT into the alerts table.
    """
    triggered = []
    for rule in RULES:
        try:
            message = rule.check(payload)
            if message:
                logger.warning(
                    "[ALERT] %s | device=%s | %s",
                    rule.alert_type, payload.deviceId, message,
                )
                triggered.append(
                    {
                        "alert_type": rule.alert_type,
                        "severity": rule.severity,
                        "message": message,
                    }
                )
        except Exception as exc:
            logger.error("Alert rule %s failed: %s", rule.alert_type, exc)
    return triggered
