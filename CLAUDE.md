# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FleetPulse is a learning project for Python microservices. It consists of two FastAPI services communicating over HTTP, deployed locally on Kubernetes.

## Common Commands

**Install dependencies (from a service directory):**
```bash
pip install -e .
# or with uv (workspace-aware):
uv sync
```

**Run a service locally:**
```bash
uvicorn apps.fleet_service.app.main:app --reload --port 8001
uvicorn apps.delivery_service.app.main:app --reload --port 8002
```

**Run all tests:**
```bash
pytest
```

**Run tests for a single service:**
```bash
pytest apps/fleet_service/test
pytest apps/delivery_service/test
```

**Run tests by marker:**
```bash
pytest -m routes
pytest -m "unit and not integration"
```

**Deploy to local Kubernetes (Docker Desktop required):**
```bash
./deploy-local.bat   # builds images, deploys, starts port-forwarding
./shutdown-local.bat # tears everything down
```

**Run with Docker Compose (lighter-weight alternative to Kubernetes):**
```bash
docker compose up --build
docker compose down
```
See `DEPLOYMENT.md` for details on both options.

## Architecture

Two independent microservices with in-memory storage (no database).

### Fleet Service (port 8001)
Manages trucks. Layers: `routes → service → repository → models`.
- `POST /trucks`, `GET /trucks` — public API
- `POST /internal/truck-assignments` — called by Delivery Service only

### Delivery Service (port 8002)
Manages deliveries. Same layer structure, plus a `fleet_client` that makes async HTTP calls to Fleet Service.
- `POST /deliveries`, `GET /deliveries`, `GET /deliveries/{id}`
- On delivery creation, it calls Fleet Service to assign a truck; delivery status becomes `ASSIGNED` or `DENIED`.

### Inter-service communication
`delivery_service/app/clients/fleet_client.py` uses `httpx` (async) to call Fleet Service. The base URL comes from the `FLEET_SERVICE_URL` env var (defaults to `http://127.0.0.1:8001` for local, non-containerized runs).

### Data models
- **Truck:** `id`, `plate_number`, `capacity_kg`, `status` (`AVAILABLE` / `IN_USE` / `IN_REPAIR`)
- **Delivery:** `id`, `client_id`, `pickup_location`, `dropoff_location`, `cargo_weight_kg`, `requested_date`, `status` (`REQUESTED` / `ASSIGNED` / `DENIED` / `COMPLETED`), `assigned_truck_id`

## Test Conventions

pytest markers (defined in `pytest.ini`):
| Marker | Meaning |
|---|---|
| `unit` | Fast, isolated |
| `integration` | Crosses layers or calls external systems |
| `routes` | FastAPI route behavior (uses `TestClient`) |
| `service` | Service layer business logic |
| `repository` | Repository/storage behavior |

Route tests use FastAPI `TestClient`. External clients (e.g. `fleet_client`) are monkeypatched. Repository fixtures use `autouse` to reset in-memory state between tests.

## Workspace Layout

```
pyproject.toml          # uv workspace root — members: apps/*
pytest.ini              # testpaths for both services
apps/
  fleet_service/
    app/
      truck/            # routes, service, repository, models
      assignment/       # internal assignment endpoint
    test/
    deployment/         # K8s YAML manifests + Dockerfile
  delivery_service/
    app/
      delivery/         # routes, service, repository, models
      fleet/            # fleet_client (httpx)
    test/
    deployment/
api_collection/         # Bruno API collection (YAML)
```

## Project Status

**Done:**
- Fleet Service — create truck (`POST /trucks`), list trucks (`GET /trucks`), internal truck assignment (`POST /internal/truck-assignments`)
- Delivery Service — create delivery (`POST /deliveries`), list deliveries (`GET /deliveries`), get delivery by id (`GET /deliveries/{id}`)
- All routes, services, and repositories covered by pytest
- Local deployment via Kubernetes (`deploy-local.bat` / `shutdown-local.bat`) and via Docker Compose (`docker-compose.yml`)
- Fleet Service URL externalized via `FLEET_SERVICE_URL` env var (was previously hardcoded)

**In progress:**
- Kafka integration for async event-driven communication between services (topics, producers, consumers)
- Updating Docker images and `docker-compose.yml` to include a Kafka service
- Integration tests for Kafka interactions

**Next up:**
- Monitoring and logging (e.g., Prometheus/Grafana, ELK stack)