.PHONY: help install run dev down build up logs clean test

# ──────────────────────────────────────────────
# Default target
# ──────────────────────────────────────────────
help:
	@echo ""
	@echo "  IoT Telemetry — Available Commands"
	@echo "  ─────────────────────────────────────────────"
	@echo "  Local Dev"
	@echo "    make install     Install Python dependencies"
	@echo "    make run         Start backend (uvicorn)"
	@echo "    make dev         Start backend with --reload"
	@echo "    make frontend    Open frontend in browser"
	@echo ""
	@echo "  Docker"
	@echo "    make build       Build Docker images"
	@echo "    make up          Start all containers (detached)"
	@echo "    make down        Stop all containers"
	@echo "    make logs        Tail container logs"
	@echo "    make restart     Down + up"
	@echo ""
	@echo "  Database"
	@echo "    make db-reset    Delete local SQLite DB"
	@echo ""
	@echo "  Testing"
	@echo "    make test        Run sample API requests"
	@echo "    make test-alert  Send payload that triggers all alerts"
	@echo ""
	@echo "  Cleanup"
	@echo "    make clean       Remove DB, cache, and Docker volumes"
	@echo ""

# ──────────────────────────────────────────────
# Local Dev
# ──────────────────────────────────────────────
install:
	pip install -r backend/requirements.txt

run:
	cd backend && uvicorn main:app --host 0.0.0.0 --port 8000

dev:
	cd backend && uvicorn main:app --host 0.0.0.0 --port 8000 --reload

frontend:
	@echo "Opening frontend..."
	@open frontend/index.html 2>/dev/null || xdg-open frontend/index.html 2>/dev/null || \
		echo "Open frontend/index.html manually in your browser."

# ──────────────────────────────────────────────
# Docker
# ──────────────────────────────────────────────
build:
	docker compose build

up:
	docker compose up --build -d
	@echo ""
	@echo "  Frontend  →  http://localhost:3000"
	@echo "  API docs  →  http://localhost:8000/docs"
	@echo "  Health    →  http://localhost:8000/health"
	@echo ""

down:
	docker compose down

logs:
	docker compose logs -f

restart: down up

# ──────────────────────────────────────────────
# Database
# ──────────────────────────────────────────────
db-reset:
	rm -f backend/telemetry.db
	@echo "Local database deleted. It will be recreated on next run."

# ──────────────────────────────────────────────
# Testing (curl)
# ──────────────────────────────────────────────
test:
	@echo "\n── POST normal telemetry ──"
	curl -s -X POST http://localhost:8000/telemetry \
		-H "Content-Type: application/json" \
		-d '{"deviceId":"AC-1001","timestamp":"2026-06-10T10:30:00Z","temperature":29.5,"energyConsumption":4.8,"voltage":230,"current":6.2,"status":"online"}' \
		| python3 -m json.tool

	@echo "\n── GET latest reading ──"
	curl -s http://localhost:8000/devices/AC-1001/latest | python3 -m json.tool

	@echo "\n── GET device summary ──"
	curl -s http://localhost:8000/devices/AC-1001/summary | python3 -m json.tool

	@echo "\n── GET alerts ──"
	curl -s http://localhost:8000/alerts | python3 -m json.tool

	@echo "\n── Duplicate (idempotency check) ──"
	curl -s -X POST http://localhost:8000/telemetry \
		-H "Content-Type: application/json" \
		-d '{"deviceId":"AC-1001","timestamp":"2026-06-10T10:30:00Z","temperature":29.5,"energyConsumption":4.8,"voltage":230,"current":6.2,"status":"online"}' \
		| python3 -m json.tool

	@echo "\n── Validation error (temp out of range) ──"
	curl -s -X POST http://localhost:8000/telemetry \
		-H "Content-Type: application/json" \
		-d '{"deviceId":"AC-1001","timestamp":"2026-06-10T10:35:00Z","temperature":999,"energyConsumption":4.8,"voltage":230,"current":6.2,"status":"online"}' \
		| python3 -m json.tool

test-alert:
	@echo "\n── POST telemetry that triggers ALL alerts ──"
	curl -s -X POST http://localhost:8000/telemetry \
		-H "Content-Type: application/json" \
		-d '{"deviceId":"AC-1002","timestamp":"2026-06-10T11:00:00Z","temperature":55.0,"energyConsumption":12.5,"voltage":170,"current":16.0,"status":"offline"}' \
		| python3 -m json.tool

	@echo "\n── GET critical alerts ──"
	curl -s "http://localhost:8000/alerts?severity=critical" | python3 -m json.tool

# ──────────────────────────────────────────────
# Cleanup
# ──────────────────────────────────────────────
clean: db-reset
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	docker compose down -v 2>/dev/null || true
	@echo "Clean complete."