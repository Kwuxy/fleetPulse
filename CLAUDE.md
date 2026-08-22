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
./infra/k8s/deploy-local.bat   # builds images, deploys, starts port-forwarding
./infra/k8s/shutdown-local.bat # tears everything down
```

**Run with Docker Compose (lighter-weight alternative to Kubernetes):**
```bash
docker compose up --build
docker compose down
```
See `infra/DEPLOYMENT.md` for details on both options.

**Check Kafka topics were created (after `docker compose up`):**
```bash
docker compose logs kafka_init
docker compose exec kafka kafka-topics --list --bootstrap-server localhost:9092
```

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
`delivery_service/app/clients/fleet_client.py` uses `httpx` (async) to call Fleet Service. The base URL comes from the `FLEET_SERVICE_URL` env var (defaults to `http://127.0.0.1:8001` for local, non-containerized runs). This is still the live path for truck assignment today — Kafka (below) is running alongside it but not yet wired into the assignment flow.

### Kafka
A single-node broker (`confluentinc/cp-kafka`, KRaft mode — no Zookeeper) runs as the `kafka` service in `docker-compose.yml`, with a combined `broker,controller` role. It exposes one client listener (`CLIENT`, internal to the compose network only — nothing is published to the host) and one `CONTROLLER` listener for KRaft's internal Raft consensus.

Topics are created explicitly and automatically on startup by a one-shot `kafka_init` service, which runs `infra/kafka/create_topics.sh` (a POSIX `sh` script, idempotent via `--if-not-exists`) once `kafka` reports healthy, then exits. Both app services `depends_on` both `kafka` (`condition: service_healthy`) and `kafka_init` (`condition: service_completed_successfully`), so they don't start until the broker is up and topics exist.

Topics defined so far (1 partition, replication factor 1 — single-broker local setup):
- `truck-assignment-requested` — intended: Delivery Service produces, Fleet Service consumes
- `truck-assignment-completed` — intended: Fleet Service produces, Delivery Service consumes

These aren't produced/consumed by application code yet — see Project Status below.

A `redpanda_console` service (Redpanda Console, image `docker.redpanda.com/redpandadata/console`) is also in `docker-compose.yml`, giving a web UI at `http://localhost:8080` for browsing topics/messages and consumer groups on the local broker. It connects to `kafka:9092` and waits on the same `kafka` (healthy) / `kafka_init` (completed) conditions as the app services.

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
infra/
  kafka/
    create_topics.sh    # explicit, versioned topic creation — run automatically by the kafka_init service
  k8s/
    deploy-local.bat    # builds images, deploys to K8s, starts port-forwarding
    shutdown-local.bat  # tears down the K8s deployment
  DEPLOYMENT.md         # local dev setup: Docker Compose vs Kubernetes
docker-compose.yml       # fleet_service, delivery_service, kafka (KRaft), kafka_init, redpanda_console
```

## Project Status

**Done:**
- Fleet Service — create truck (`POST /trucks`), list trucks (`GET /trucks`), internal truck assignment (`POST /internal/truck-assignments`)
- Delivery Service — create delivery (`POST /deliveries`), list deliveries (`GET /deliveries`), get delivery by id (`GET /deliveries/{id}`)
- All routes, services, and repositories covered by pytest
- Local deployment via Kubernetes (`infra/k8s/deploy-local.bat` / `infra/k8s/shutdown-local.bat`) and via Docker Compose (`docker-compose.yml`)
- Fleet Service URL externalized via `FLEET_SERVICE_URL` env var (was previously hardcoded)
- Local Kafka broker (single-node, KRaft mode) added to `docker-compose.yml`, with the two truck-assignment topics created explicitly and automatically via the `kafka_init` service — see Architecture > Kafka
- Redpanda Console added to `docker-compose.yml` and verified against a running stack (`http://localhost:8080`, correctly sees both truck-assignment topics) — see Architecture > Kafka

**In progress / Next up:**
- Define what "tests for Kafka" means for this project, then add them
- Move truck assignment from the synchronous `fleet_client` HTTP call to the `truck-assignment-requested` / `truck-assignment-completed` Kafka topics, and test it
- Externalize the Kafka URL in `infra/kafka/create_topics.sh` via an env var instead of the hardcoded `kafka:9092` (already flagged by a `TODO` in the script)
- Add persistence for Fleet/Delivery Services (currently in-memory only, lost on restart) and for Kafka (currently no volume, flagged by the `TODO` in `docker-compose.yml`)

**Later:**
- Monitoring and logging (e.g., Prometheus/Grafana, ELK stack)