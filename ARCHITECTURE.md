# IoT Telemetry System — Technical Design Document

## 1. Overview

This document covers the **High-Level Design (HLD)**, **Low-Level Design (LLD)**, and production-grade architecture for the IoT Telemetry platform built for LivingThings / iCapotech.

The system ingests telemetry from IoT devices (temperature, voltage, current, energy, status), validates and stores it, runs alert rules, and broadcasts live data to frontend clients over WebSocket.

---

## 2. High-Level Architecture (Production)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              IoT Devices (Field)                              │
│   AC-1001, AC-1002, ...  →  MQTT Broker (EMQX / AWS IoT Core)               │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     │ MQTT topics: devices/{id}/telemetry
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                           Ingestion Layer                                     │
│  MQTT Bridge / AWS IoT Rule  →  Kafka (MSK / Confluent)                      │
│  Topic: iot.telemetry.raw                                                    │
│  Partitioned by device_id for ordering                                       │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     │
                    ┌────────────────┴─────────────────┐
                    ▼                                   ▼
        ┌─────────────────────┐             ┌─────────────────────┐
        │  Telemetry Consumer │             │   Alert Consumer    │
        │  (FastAPI Worker)   │             │  (FastAPI Worker)   │
        │  - Validate         │             │  - Rule evaluation  │
        │  - Deduplicate      │             │  - Notify channels  │
        │  - Write to DB      │             │  - PagerDuty/SNS    │
        └──────────┬──────────┘             └──────────┬──────────┘
                   │                                   │
                   ▼                                   ▼
        ┌─────────────────────┐             ┌─────────────────────┐
        │  TimescaleDB /      │             │  Alerts Table       │
        │  PostgreSQL         │             │  (PostgreSQL)       │
        │  (hypertable on     │             │                     │
        │   timestamp)        │             │                     │
        └──────────┬──────────┘             └─────────────────────┘
                   │
        ┌──────────┴──────────┐
        │   API Service       │
        │  (FastAPI / uvicorn)│
        │  POST /telemetry    │
        │  GET /devices/:id/  │
        │  GET /alerts        │
        │  WS /ws/telemetry   │
        └──────────┬──────────┘
                   │
        ┌──────────▼──────────┐
        │  Frontend SPA       │
        │  (WebSocket client) │
        │  Live telemetry     │
        │  dashboard          │
        └─────────────────────┘
```

### 2.1 Component Roles

| Component | Responsibility |
|-----------|---------------|
| **MQTT Broker** | Accepts device connections, enforces auth, fans out to Kafka |
| **Kafka** | Durable event log, ordered per device, enables replay and multi-consumer |
| **Telemetry Consumer** | Validates, deduplicates, writes to TimescaleDB |
| **Alert Consumer** | Evaluates rules, writes alerts, pushes notifications |
| **API Service** | REST + WebSocket layer; thin; does not own heavy computation |
| **TimescaleDB** | Time-series data store; automatic partitioning by time |
| **Redis Pub/Sub** | Fanout for WebSocket broadcasts across multiple API pods |
| **Frontend SPA** | Single-page dashboard; pure WS consumer |

---

## 3. Data Model / Schema

### 3.1 `telemetry` (main time-series table)

```sql
CREATE TABLE telemetry (
    id            BIGSERIAL PRIMARY KEY,
    device_id     TEXT        NOT NULL,
    timestamp     TIMESTAMPTZ NOT NULL,
    temperature   REAL        NOT NULL,
    energy        REAL        NOT NULL,    -- kWh
    voltage       REAL        NOT NULL,    -- V
    current       REAL        NOT NULL,    -- A
    status        TEXT        NOT NULL,
    received_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (device_id, timestamp)          -- idempotency key
);

-- TimescaleDB hypertable (production):
SELECT create_hypertable('telemetry', 'timestamp');

-- Composite index for per-device queries
CREATE INDEX ON telemetry (device_id, timestamp DESC);
```

### 3.2 `device_latest` (hot row per device)

```sql
CREATE TABLE device_latest (
    device_id     TEXT    PRIMARY KEY,
    telemetry_id  BIGINT  REFERENCES telemetry(id),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3.3 `alerts`

```sql
CREATE TABLE alerts (
    id            BIGSERIAL PRIMARY KEY,
    device_id     TEXT        NOT NULL,
    alert_type    TEXT        NOT NULL,    -- HIGH_TEMPERATURE, ENERGY_SPIKE, ...
    message       TEXT        NOT NULL,
    severity      TEXT        NOT NULL,    -- critical | warning | info
    telemetry_id  BIGINT      REFERENCES telemetry(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON alerts (device_id, created_at DESC);
CREATE INDEX ON alerts (severity, created_at DESC);
```

---

## 4. Telemetry Data Flow

```
Device  →  POST /telemetry (or MQTT)
        →  Validation (Pydantic schema)
        →  INSERT telemetry (ON CONFLICT DO NOTHING  ← idempotency)
        →  UPSERT device_latest
        →  Alert rule evaluation
        →  INSERT alerts (if triggered)
        →  WebSocket broadcast to connected clients
        →  Return 201 with telemetry_id + alerts_triggered
```

### 4.1 Late Event Handling

- The `timestamp` field on the payload is the **device timestamp** (source-of-truth).
- `received_at` is the server ingestion time.
- Late events (device_timestamp < now - 5min) are accepted but flagged.
- Ordering queries always use `ORDER BY timestamp` not `received_at`.
- No `LAST_VALUE` window function assumptions; TimescaleDB's continuous aggregates use `timestamp`.

### 4.2 Duplicate Handling

- `UNIQUE(device_id, timestamp)` on the telemetry table.
- `ON CONFLICT DO NOTHING` in the INSERT.
- API returns 201 with `"message": "Duplicate telemetry — already processed"` without error.
- Kafka consumers use **exactly-once semantics** (idempotent producer + transactional consumer) in production.

### 4.3 Retry Strategy

- Devices retry with exponential backoff + jitter.
- Idempotency key: `device_id + timestamp`.
- Duplicate retries are safely no-ops at the DB layer.

---

## 5. Alerting Logic

### 5.1 Implemented Rules

| Rule | Trigger | Severity |
|------|---------|----------|
| `HIGH_TEMPERATURE` | temperature > 40°C | critical |
| `LOW_TEMPERATURE` | temperature < -10°C | warning |
| `ENERGY_SPIKE` | energyConsumption > 10 kWh | critical |
| `HIGH_ENERGY` | energyConsumption > 8 kWh | warning |
| `DEVICE_OFFLINE` | status in {offline, error} | critical |
| `VOLTAGE_ANOMALY` | voltage < 180V or > 260V | warning |
| `CURRENT_ANOMALY` | current > 15A | warning |

### 5.2 Production Alert Routing

```
Alert fired → alert_consumer → writes to alerts table
                             → publishes to SNS/PagerDuty (critical)
                             → sends Slack notification (warning)
                             → updates device health score
```

---

## 6. WebSocket Design

- Endpoint: `ws://localhost:8000/ws/telemetry`
- Server-push only; clients listen.
- `ConnectionManager` singleton tracks all open sockets.
- On `POST /telemetry`, after DB commit, `await manager.broadcast(...)` fans out to all clients.

**Production pattern (multi-pod):**
```
API Pod 1  ─┐
API Pod 2  ─┤─→  Redis Pub/Sub (channel: telemetry:live)  ←─  each pod subscribes
API Pod N  ─┘       and broadcasts to its local WS clients
```

---

## 7. Validation & Error Handling

| Scenario | Response |
|----------|----------|
| Missing required field | 422 Unprocessable Entity with field errors |
| Temperature out of range [-50, 150] | 422 with message |
| Voltage out of range [0, 500] | 422 with message |
| Current out of range [0, 100] | 422 with message |
| Energy out of range [0, 1000] | 422 with message |
| Invalid status value | 422 with allowed set |
| Duplicate telemetry | 201 with "already processed" note |
| DB failure | 500 with generic message (details logged) |

---

## 8. Logging, Monitoring, Tracing

### 8.1 Implemented (Local)

- Structured logging via Python `logging` module: `%(asctime)s [%(levelname)s] %(name)s - %(message)s`
- Every ingested telemetry logs: device_id, telemetry_id, alert count, WS client count.
- Every alert logs at WARNING level.

### 8.2 Production Stack

| Concern | Tool |
|---------|------|
| Log aggregation | AWS CloudWatch / ELK Stack |
| Metrics | Prometheus + Grafana dashboards |
| Distributed tracing | OpenTelemetry → Jaeger / AWS X-Ray |
| Uptime / alerting | PagerDuty / OpsGenie |
| DB query analysis | pg_stat_statements |

Key metrics to track:
- `telemetry.ingestion.rate` (events/sec per device)
- `telemetry.ingestion.latency` (p50/p95/p99)
- `alerts.triggered.count` (by type)
- `websocket.connections.active`
- `db.write.latency`

---

## 9. Scaling Strategy (Thousands of Devices)

### 9.1 Horizontal Scaling

```
Load Balancer (ALB)
    ├── API Pod 1 (FastAPI + uvicorn workers)
    ├── API Pod 2
    └── API Pod N

WS sticky sessions: ALB stickiness or separate WS tier
```

### 9.2 Database Scaling

- **TimescaleDB** with hypertables auto-partitions data by time.
- **Read replicas** for GET endpoints; writes go to primary.
- **Retention policy**: raw data retained 90 days; daily aggregates retained indefinitely.
- **Connection pooling**: PgBouncer in transaction mode.

### 9.3 Ingestion at Scale

```
10,000 devices × 1 reading/min = 166 events/sec  →  Kafka handles easily
10,000 devices × 10 readings/min = 1,666 events/sec  →  scale Kafka partitions
```

- Kafka topic `iot.telemetry.raw` with `N = device_count / 100` partitions minimum.
- Partition key = `device_id` ensures ordering per device.
- Consumer group auto-scales workers.

### 9.4 Offline Device Detection

- Scheduled job (Celery Beat / APScheduler) runs every minute:
  ```sql
  SELECT device_id FROM device_latest
  WHERE updated_at < NOW() - INTERVAL '5 minutes'
  ```
- Creates `DEVICE_OFFLINE` alert if not already created in last 10 min.

---

## 10. Implemented Vertical Slice (Local Dev)

The working implementation uses:

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Runtime | Python 3.11 + FastAPI | Async-native, high performance |
| DB | SQLite (aiosqlite) | Zero-install for local dev |
| WS | FastAPI WebSocket | Built-in, no extra dep |
| Validation | Pydantic v2 | Fast, declarative |
| Server | Uvicorn | ASGI, production-grade |

**Schema equivalent** in SQLite mirrors the PostgreSQL design exactly — swapping `REAL` → `DOUBLE PRECISION` and `BIGSERIAL` → `INTEGER AUTOINCREMENT` for production.

---

## 11. AI-Assisted Coding Disclosure

AI tools were used in this project as follows:

| Area | AI Contribution | Human Review |
|------|----------------|--------------|
| Alert rule structure | Generated initial rule dataclass pattern | Reviewed, added severity levels and all 6 rules |
| WebSocket manager | Suggested lock-based connection set | Added dead-connection cleanup and connection count |
| SQL schema | Suggested base schema | Added UNIQUE constraint for idempotency, indexes, device_latest pattern |
| Frontend HTML | Generated base layout | Rewrote status pill logic, alert rendering, test form, reconnect logic |
| Pydantic validators | Suggested `field_validator` pattern | Added all range checks and status allow-list |

All generated code was manually reviewed for correctness, security (no raw SQL string interpolation — all parameterised), and alignment with the assignment requirements.