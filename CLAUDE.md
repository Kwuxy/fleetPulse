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
`delivery_service/app/clients/fleet_client.py` uses `httpx` (async) to call Fleet Service's `POST /internal/truck-assignments`. The base URL comes from the `FLEET_SERVICE_URL` env var (defaults to `http://127.0.0.1:8001` for local, non-containerized runs). This is no longer the live path for truck assignment — `create_delivery` now produces to Kafka instead (see Architecture > Kafka below) — but the module and its `except TimeoutException` handling in `delivery_routes.py` haven't been deleted yet; that's next up (see Project Status).

### Kafka
A single-node broker (`confluentinc/cp-kafka`, KRaft mode — no Zookeeper) runs as the `kafka` service in `docker-compose.yml`, with a combined `broker,controller` role. It exposes three listeners: `CLIENT` (`kafka:9092`, for other containers — used by `fleet_service`, `delivery_service`, `kafka_init`, `redpanda_console`), `EXTERNAL` (published to the host as `localhost:9094`, so non-containerized local runs, e.g. plain `uvicorn`, can reach the broker too — Kafka's advertised-listener metadata means a single listener can't correctly serve both container and host clients), and `CONTROLLER` for KRaft's internal Raft consensus.

Topics are created explicitly and automatically on startup by a one-shot `kafka_init` service, which runs `infra/kafka/create_topics.sh` (a POSIX `sh` script, idempotent via `--if-not-exists`) once `kafka` reports healthy, then exits. Both app services `depends_on` both `kafka` (`condition: service_healthy`) and `kafka_init` (`condition: service_completed_successfully`), so they don't start until the broker is up and topics exist.

Topics defined so far (1 partition, replication factor 1 — single-broker local setup):
- `truck-assignment-requested` — intended: Delivery Service produces, Fleet Service consumes
- `truck-assignment-completed` — intended: Fleet Service produces, Delivery Service consumes

Both topics are now produced and consumed end-to-end by application code: `truck-assignment-requested` is produced by Delivery Service and consumed by Fleet Service; `truck-assignment-completed` is produced by Fleet Service and consumed by Delivery Service.

A `redpanda_console` service (Redpanda Console, image `docker.redpanda.com/redpandadata/console`) is also in `docker-compose.yml`, giving a web UI at `http://localhost:8080` for browsing topics/messages and consumer groups on the local broker. It connects to `kafka:9092` and waits on the same `kafka` (healthy) / `kafka_init` (completed) conditions as the app services.

### Kafka-based truck assignment

Assignment has moved off the synchronous `fleet_client` HTTP call onto the two existing topics; all four flow steps below are implemented end-to-end — see Project Status for exact state. The only remaining loose end on the HTTP side is deleting the now-dead `fleet_client.py` and its stale `except TimeoutException` handling in `delivery_routes.py`.

**API semantics:** `POST /deliveries` becomes eventually consistent. It returns immediately with status `REQUESTED`; the client polls `GET /deliveries/{id}` to observe the eventual `ASSIGNED`/`DENIED` outcome.

**Client library:** `aiokafka` — async, integrates naturally with FastAPI's async handlers and `lifespan`.

**Message schemas** (JSON, key = `delivery_id` on both topics):
- `truck-assignment-requested`: `{delivery_id, cargo_weight_kg}` — same shape as today's `TruckAssignmentRequest`.
- `truck-assignment-completed`: `{delivery_id, truck_id, assigned, reason, description}` — `reason` is the coarse `TruckAssignmentFailureReason` (`INVALID_REQUEST` / `NO_AVAILABLE_TRUCK`); `description` carries the human-readable detail (`str(e)` from the originating exception) so specifics aren't lost behind the coarse code.

**Flow:**
1. Delivery Service's `create_delivery` produces to `truck-assignment-requested` instead of calling `fleet_client`, saves the delivery as `REQUESTED`, and returns immediately.
2. Fleet Service's new consumer on `truck-assignment-requested` calls the existing `assignment_service.assign_truck_to_delivery` (layering unchanged), catching validation errors (`InvalidCargoWeight`, `UnknownDelivery`) and mapping them to a `DENIED` completion instead of raising.
3. Fleet Service produces the result to `truck-assignment-completed`.
4. Delivery Service's new consumer on `truck-assignment-completed` looks up the delivery by `delivery_id` and updates its status to `ASSIGNED`/`DENIED`.
5. Both consumers run as background tasks started/stopped via FastAPI `lifespan`.

**Error handling:** `TruckAssignmentFailureReason` gains `INVALID_REQUEST` alongside `NO_AVAILABLE_TRUCK`, so every request resolves to `ASSIGNED` or `DENIED` — no silent stuck-in-`REQUESTED` state on validation failure.

**Offset commit contract:** `kafka_client.py` defines `QueueMessageStatus` (`CONSUMED` / `FAILED`) as the return-type contract between the generic consume loop (`_run`) and whatever handler is passed to `start_consuming`. The consumer is created with `enable_auto_commit=False`, and `_run` only calls `consumer.commit()` when the handler returns `CONSUMED` — so a message counts as done only once it's been fully handled (including being resolved to a `DENIED` completion), not merely received. A handler exception that isn't caught internally propagates out of `_run`'s `try` (logged via `logger.exception`, nothing committed), so that message is redelivered on the next poll/restart. `handle_truck_assignment_requested` uses this by catching `UnknownDelivery`/`InvalidCargoWeight`/`NoTruckAvailable` itself and returning `CONSUMED` in all three cases — deterministic business rejections are meant to resolve, not retry forever.

**Fate of `/internal/truck-assignments`:** likely retired once the consumer-based flow is live; may be kept temporarily for manual testing during the transition.

**Test strategy:**
- New `kafka` pytest marker, combined with the existing `unit`/`integration` markers.
- `kafka` + `unit`: mocked `aiokafka` producer/consumer, testing call-shape (correct topic/payload on produce) and message-handling logic (correct status transition on consume) in both services. Runs every time, no external dependency.
- `kafka` + `integration`: a small number of true round-trip smoke tests against a disposable broker spun up via `testcontainers[kafka]` — not the docker-compose Kafka instance, to keep tests isolated and not dependent on the stack already being up.
- Rationale: verifying Kafka itself works isn't this project's responsibility (the broker health check plus `kafka_init`'s explicit topic creation already cover that); verifying *our* producer/consumer contract with Kafka is.

### Data models
- **Truck:** `id`, `plate_number`, `capacity_kg`, `status` (`AVAILABLE` / `IN_USE` / `IN_REPAIR`)
- **Delivery:** `id`, `client_id`, `pickup_location`, `dropoff_location`, `cargo_weight_kg`, `requested_date`, `status` (`REQUESTED` / `ASSIGNED` / `DENIED` / `COMPLETED`), `assigned_truck_id`, `denial_reason` (Delivery Service's own `DeliveryDenialReason` enum — currently mirrors `TruckAssignmentFailureReason`'s values but is a deliberately separate type, expected to grow values beyond Fleet Service's technical reasons as the product develops), `denial_description` (free-text detail, set only when `status` is `DENIED`)

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
      routes/           # truck_routes, assignment_routes
      services/         # truck_service, assignment_service
      repositories/     # truck_repository, assignment_repository
      models/           # truck, assignment
      clients/          # kafka_client (aiokafka) — consumer (group_id, manual commit
                         #   via QueueMessageStatus) and producer both implemented
      consumers/        # assignment_consumer — Kafka-triggered entry point into
                         #   assignment_service, parallel to assignment_routes; implemented
      producers/        # assignment_producer — produces TruckAssignmentCompleted onto
                         #   truck-assignment-completed
    test/
    deployment/         # K8s YAML manifests + Dockerfile
  delivery_service/
    app/
      routes/           # delivery_routes
      services/         # delivery_service
      repositories/     # delivery_repository
      models/           # delivery, truck_assignment (Delivery Service's own copies of
                         #   the Kafka message schemas — TruckAssignmentRequest,
                         #   TruckAssignmentCompleted, TruckAssignmentFailureReason —
                         #   deliberately not shared with Fleet Service's models)
      clients/          # fleet_client (httpx, now dead code — pending removal),
                         #   kafka_client (aiokafka, consumer + producer)
      consumers/        # assignment_consumer — handles truck-assignment-completed,
                         #   updates delivery status via delivery_service
      producers/        # assignment_producer — produces TruckAssignmentRequest onto
                         #   truck-assignment-requested
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
- Fleet Service Kafka consumer for `truck-assignment-requested` implemented — see Architecture > Kafka > Kafka-based truck assignment:
  - `app/clients/kafka_client.py` — `start_consuming(handler)`/`stop_consuming()`, consumer created with an explicit `group_id` and `enable_auto_commit=False`; `_run` commits only when the handler returns `QueueMessageStatus.CONSUMED` (see Architecture > Kafka > Offset commit contract)
  - `app/consumers/assignment_consumer.py` — `handle_truck_assignment_requested(msg: dict)` parses the raw dict into a `TruckAssignmentRequest`, calls the existing `assignment_service.assign_truck_to_delivery` (layering unchanged), and maps `UnknownDelivery`/`InvalidCargoWeight` → `INVALID_REQUEST` and `NoTruckAvailable` → `NO_AVAILABLE_TRUCK` via `TruckAssignmentCompleted.get_failed`, success via `.get_success` — every case resolves and commits, none left stuck
  - `app/main.py`'s import bug (relative instead of `app.`-rooted imports) is fixed
  - `TruckAssignmentFailureReason.INVALID_REQUEST` added alongside `NO_AVAILABLE_TRUCK`
- fleet_service switched from `print()` to Python's `logging` module: `logging.basicConfig` in `app/main.py` (level via `LOG_LEVEL` env var, defaults to `INFO`), module-level `logger = logging.getLogger(__name__)` in `kafka_client.py` and `assignment_consumer.py`
- Fleet Service Kafka producer for `truck-assignment-completed` implemented, completing the flow end-to-end:
  - `app/clients/kafka_client.py` gained the producer half (`start_producer`/`stop_producer`/`get_producer`), mirroring Delivery Service's; `app/main.py`'s lifespan now starts/stops both the consumer and the producer
  - `app/producers/assignment_producer.py` — `produce_truck_assignment_completed(...)` sends the actual message (key = `delivery_id`, value = `.model_dump()`); the log-only stub that used to live in `assignment_consumer.py` is gone, replaced by real calls into this module
  - `TruckAssignmentCompleted` (`app/models/assignment.py`) gained `delivery_id` (for correlation) and `description` (human-readable detail via `str(e)`, alongside the existing coarse `reason`); `get_failed`/`get_success` updated to take `delivery_id`
- Delivery Service Kafka consumer for `truck-assignment-completed` implemented, mirroring Fleet Service's consumer structure:
  - `app/clients/kafka_client.py` gained the consumer half; `app/main.py`'s lifespan now starts/stops both the producer and this consumer
  - `app/models/truck_assignment.py` — Delivery Service's own `TruckAssignmentRequest`/`TruckAssignmentCompleted`/`TruckAssignmentFailureReason`, deliberately not shared with Fleet Service's copies (same reasoning as Fleet Service owning its own `TruckAssignmentRequest` for the other topic)
  - `app/consumers/assignment_consumer.py` — `handle_truck_assignment_completed(msg: dict)` parses into that model and calls `delivery_service.update_delivery_with_truck_assignment`; both a `ValidationError` on parse and a `NotFoundException` (unknown `delivery_id`) resolve to `CONSUMED`, matching Fleet Service's offset-commit contract
- `Delivery` model gained `denial_reason` (Delivery Service's own `DeliveryDenialReason` enum — currently mirrors `TruckAssignmentFailureReason`'s values, expected to diverge and grow as denial causes beyond truck assignment are added) and `denial_description`, both set by `update_delivery_with_truck_assignment` when a delivery is denied

**In progress / Next up:**
- Remove the now-dead synchronous HTTP path: `delivery_service/app/clients/fleet_client.py` and the stale `except TimeoutException` handling in `delivery_routes.py` — `create_delivery` no longer calls `fleet_client`, it only produces to Kafka
- Malformed messages (pydantic `ValidationError`) on both `truck-assignment-requested` and `truck-assignment-completed` are currently logged and committed (i.e. dropped) rather than routed anywhere — whether a dead-letter topic is needed is still open (flagged by `TODO`s in both consumers)
- Tests for the Fleet Service Kafka consumer path (message parsing, exception→reason mapping, commit-vs-not behavior) — none written yet
- Tests for the Delivery Service Kafka consumer path (`handle_truck_assignment_completed`) and producer (`produce_truck_assignment_requested`) — none written yet
- Delivery Service Kafka producer error handling isn't designed yet — what happens on a failed/unacknowledged send (broker unavailable, produce timeout), and whether a dead-letter approach is needed for messages that are never successfully read/processed downstream
- Add/update tests for `POST /deliveries` against its new eventually-consistent behavior (returns `REQUESTED` immediately) — currently untested
- Externalize the Kafka URL in `infra/kafka/create_topics.sh` via an env var instead of the hardcoded `kafka:9092` (already flagged by a `TODO` in the script)
- Add persistence for Fleet/Delivery Services (currently in-memory only, lost on restart) and for Kafka (currently no volume, flagged by the `TODO` in `docker-compose.yml`)

**Later:**
- Monitoring and logging (e.g., Prometheus/Grafana, ELK stack)