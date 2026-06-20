# IoT Telemetry System — README

## Quick Start

### 1. Install Python dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Start the backend

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The server starts, initialises the SQLite database (`telemetry.db`) automatically, and is ready at `http://localhost:8000`.

Interactive API docs: `http://localhost:8000/docs`

### 3. Open the frontend

Open `frontend/index.html` directly in a browser (no build step needed):

```bash
# macOS
open frontend/index.html

# Linux
xdg-open frontend/index.html

# Or just drag the file into a browser window
```

The page connects to `ws://localhost:8000/ws/telemetry` automatically and shows live sensor data as you POST telemetry.

---

## API Reference

### POST /telemetry — Ingest a reading

```bash
curl -X POST http://localhost:8000/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "deviceId": "AC-1001",
    "timestamp": "2026-06-10T10:30:00Z",
    "temperature": 29.5,
    "energyConsumption": 4.8,
    "voltage": 230,
    "current": 6.2,
    "status": "online"
  }'
```

**Trigger HIGH_TEMPERATURE alert:**
```bash
curl -X POST http://localhost:8000/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "deviceId": "AC-1002",
    "timestamp": "2026-06-10T10:31:00Z",
    "temperature": 55.0,
    "energyConsumption": 4.8,
    "voltage": 230,
    "current": 6.2,
    "status": "online"
  }'
```

**Trigger DEVICE_OFFLINE alert:**
```bash
curl -X POST http://localhost:8000/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "deviceId": "AC-1003",
    "timestamp": "2026-06-10T10:32:00Z",
    "temperature": 28.0,
    "energyConsumption": 4.8,
    "voltage": 230,
    "current": 6.2,
    "status": "offline"
  }'
```

**Trigger ENERGY_SPIKE alert:**
```bash
curl -X POST http://localhost:8000/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "deviceId": "AC-1001",
    "timestamp": "2026-06-10T10:33:00Z",
    "temperature": 29.5,
    "energyConsumption": 12.5,
    "voltage": 230,
    "current": 6.2,
    "status": "online"
  }'
```

**Validation error (temperature out of range):**
```bash
curl -X POST http://localhost:8000/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "deviceId": "AC-1001",
    "timestamp": "2026-06-10T10:34:00Z",
    "temperature": 999,
    "energyConsumption": 4.8,
    "voltage": 230,
    "current": 6.2,
    "status": "online"
  }'
```

---

### GET /devices/:deviceId/latest — Latest reading for a device

```bash
curl http://localhost:8000/devices/AC-1001/latest
```

---

### GET /devices/:deviceId/summary — Aggregated stats

```bash
curl http://localhost:8000/devices/AC-1001/summary
```

---

### GET /alerts — All alerts (paginated, filterable)

```bash
# All alerts
curl http://localhost:8000/alerts

# Filter by device
curl "http://localhost:8000/alerts?device_id=AC-1001"

# Filter by severity
curl "http://localhost:8000/alerts?severity=critical"

# Paginate
curl "http://localhost:8000/alerts?limit=10&offset=0"
```

---

### WebSocket

Connect to: `ws://localhost:8000/ws/telemetry`

Messages are pushed automatically after each POST /telemetry:

```json
{
  "type": "telemetry",
  "data": {
    "deviceId": "AC-1001",
    "timestamp": "2026-06-10T10:30:00+00:00",
    "temperature": 29.5,
    "energyConsumption": 4.8,
    "voltage": 230.0,
    "current": 6.2,
    "status": "online"
  },
  "alerts": []
}
```

Test with wscat:
```bash
npm install -g wscat
wscat -c ws://localhost:8000/ws/telemetry
```

---

## Project Structure

```
iot-telemetry/
├── backend/
│   ├── main.py           # FastAPI app, CORS, lifespan
│   ├── database.py       # SQLite init, schema, get_db dependency
│   ├── schemas.py        # Pydantic models (request + response)
│   ├── alerting.py       # Alert rules engine
│   ├── ws_manager.py     # WebSocket connection manager
│   ├── requirements.txt
│   └── routers/
│       ├── telemetry.py  # POST /telemetry
│       ├── devices.py    # GET /devices/:id/latest|summary
│       ├── alerts.py     # GET /alerts
│       └── websocket.py  # WS /ws/telemetry
├── frontend/
│   └── index.html        # Single-page live dashboard
├── ARCHITECTURE.md       # HLD, LLD, schema, scaling, AI disclosure
└── README.md             # This file
```

## Database Schema

SQLite (local dev) — maps directly to PostgreSQL for production (see ARCHITECTURE.md).

**telemetry** — every reading stored with idempotency key (device_id + timestamp UNIQUE)  
**device_latest** — single hot row per device pointing to its most recent telemetry row  
**alerts** — every fired alert with type, severity, message, and linked telemetry_id  

## Alert Rules

| Rule | Trigger | Severity |
|------|---------|----------|
| HIGH_TEMPERATURE | temp > 40°C | critical |
| LOW_TEMPERATURE | temp < -10°C | warning |
| ENERGY_SPIKE | energy > 10 kWh | critical |
| DEVICE_OFFLINE | status = offline/error | critical |
| VOLTAGE_ANOMALY | voltage < 180V or > 260V | warning |
| CURRENT_ANOMALY | current > 15A | warning |