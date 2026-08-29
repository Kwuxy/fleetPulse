# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FleetPulse is a learning project for Python microservices. It consists of two FastAPI services that communicate asynchronously via Kafka, deployed locally via Docker Compose or Kubernetes.

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

**Run tests for a service** (each service has its own local `.venv` with `pytest` installed — the workspace-root `.venv` does not; see Test Conventions for why):
```bash
cd apps/fleet_service && .venv/Scripts/python.exe -m pytest test -q
cd apps/delivery_service && .venv/Scripts/python.exe -m pytest test -q
```

**Run tests by marker** (from inside the service directory, same interpreter as above):
```bash
.venv/Scripts/python.exe -m pytest test -m routes
.venv/Scripts/python.exe -m pytest test -m "unit and not integration"
```
Note `integration` isn't Kafka-specific — route tests (`test_truck_routes.py`, `test_delivery_routes.py`) are marked `integration` too, since they cross layers via `TestClient`, even though they don't touch Docker. To exclude only the `testcontainers`-backed Kafka round-trip tests while keeping those, use `-m "not (kafka and integration)"` instead of `-m "not integration"`.

**Run both services' tests sequentially, from the repo root:**
```bash
./run-tests.bat                                          # full suite, both services
./run-tests.bat -m "not (kafka and integration)"          # skip the Kafka container tests
```
Runs Delivery Service's tests, then Fleet Service's, one after the other, stopping at the first failure; any arguments after the script name are forwarded to both `pytest` invocations. PyCharm's `CompoundRunConfigurationType` always launches child configurations simultaneously with no setting to make it sequential, which causes Kafka container contention when both services' `kafka` + `integration` tests run at once (see Test Conventions) — this script is what a "run all tests" PyCharm configuration should point at instead (as a Batch run configuration).

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
- Also runs a Kafka consumer/producer that handles truck assignment requests from Delivery Service (see Kafka below)

### Delivery Service (port 8002)
Manages deliveries. Same layer structure, plus Kafka producer/consumer clients for talking to Fleet Service asynchronously.
- `POST /deliveries`, `GET /deliveries`, `GET /deliveries/{id}`
- On delivery creation, it produces a truck-assignment request onto Kafka and returns immediately with status `REQUESTED`; the eventual `ASSIGNED`/`DENIED` outcome arrives via a Kafka consumer and is only visible on a later `GET /deliveries/{id}`.

### Inter-service communication
Fleet Service and Delivery Service communicate exclusively via Kafka — there is no direct HTTP call between them. See Kafka below for the two topics and the message flow.

### Kafka
A single-node broker (`confluentinc/cp-kafka`, KRaft mode — no Zookeeper) runs as the `kafka` service in `docker-compose.yml`, with a combined `broker,controller` role. It exposes three listeners: `CLIENT` (`kafka:9092`, for other containers — used by `fleet_service`, `delivery_service`, `kafka_init`, `redpanda_console`), `EXTERNAL` (published to the host as `localhost:9094`, so non-containerized local runs, e.g. plain `uvicorn`, can reach the broker too — Kafka's advertised-listener metadata means a single listener can't correctly serve both container and host clients), and `CONTROLLER` for KRaft's internal Raft consensus. The `kafka:9092` value is defined once in `docker-compose.yml` via a top-level YAML anchor (`x-kafka-bootstrap: &kafka-bootstrap kafka:9092`) and referenced with `*kafka-bootstrap` from `fleet_service`'s and `delivery_service`'s `KAFKA_BOOTSTRAP_SERVERS`, `kafka_init`'s `KAFKA_BOOTSTRAP_SERVERS`, and `redpanda_console`'s `KAFKA_BROKERS` — a single source of truth rather than the literal repeated four times (plain YAML aliasing, not a Compose-specific feature; distinct from `.env`-file `${VAR}` substitution, which is for values that should vary per environment rather than a fixed in-network hostname like this one).

Topics are created explicitly by a one-shot `kafka_init` service, which runs `infra/kafka/create_topics.sh` (a POSIX `sh` script, idempotent via `--if-not-exists`) once `kafka` reports healthy, then exits. The script reads its bootstrap URL from `KAFKA_BOOTSTRAP_SERVERS` (`KAFKA_URL="${KAFKA_BOOTSTRAP_SERVERS:-kafka:9092}"`), which `kafka_init` gets from the anchor above. Both app services `depends_on` both `kafka` (`condition: service_healthy`) and `kafka_init` (`condition: service_completed_successfully`), so they don't start until the broker is up and topics exist.

Topics (1 partition, replication factor 1 — single-broker local setup):
- `truck-assignment-requested` — produced by Delivery Service, consumed by Fleet Service
- `truck-assignment-completed` — produced by Fleet Service, consumed by Delivery Service

A `redpanda_console` service (Redpanda Console, image `docker.redpanda.com/redpandadata/console`) is also in `docker-compose.yml`, giving a web UI at `http://localhost:8080` for browsing topics/messages and consumer groups on the local broker. It connects to `kafka:9092` and waits on the same `kafka` (healthy) / `kafka_init` (completed) conditions as the app services.

### Kafka-based truck assignment

**API semantics:** `POST /deliveries` is eventually consistent. It returns immediately with status `REQUESTED`; the client polls `GET /deliveries/{id}` to observe the eventual `ASSIGNED`/`DENIED` outcome.

**Client library:** `aiokafka` — async, integrates naturally with FastAPI's async handlers and `lifespan`.

**Message schemas** (JSON, key = `delivery_id` on both topics):
- `truck-assignment-requested`: `{delivery_id, cargo_weight_kg}` — same shape as `TruckAssignmentRequest`.
- `truck-assignment-completed`: `{delivery_id, truck_id, assigned, reason, description}` — `reason` is the coarse `TruckAssignmentFailureReason` (`INVALID_REQUEST` / `NO_AVAILABLE_TRUCK`); `description` carries the human-readable detail (`str(e)` from the originating exception) so specifics aren't lost behind the coarse code.

**Flow:**
1. Delivery Service's `create_delivery` produces to `truck-assignment-requested`, saves the delivery as `REQUESTED`, and returns immediately.
2. Fleet Service's consumer on `truck-assignment-requested` calls `assignment_service.assign_truck_to_delivery` (layering unchanged), catching validation errors (`InvalidCargoWeight`, `UnknownDelivery`) and mapping them to a `DENIED` completion instead of raising.
3. Fleet Service produces the result to `truck-assignment-completed`.
4. Delivery Service's consumer on `truck-assignment-completed` looks up the delivery by `delivery_id` and updates its status to `ASSIGNED`/`DENIED`.
5. Both consumers run as background tasks started/stopped via FastAPI `lifespan`.

**Error handling:** `TruckAssignmentFailureReason` has `INVALID_REQUEST` alongside `NO_AVAILABLE_TRUCK`, so every request resolves to `ASSIGNED` or `DENIED` — no silent stuck-in-`REQUESTED` state on validation failure.

**Offset commit contract:** `kafka_client.py` defines `QueueMessageStatus` (`CONSUMED` / `FAILED`) as the return-type contract between the generic consume loop (`_run`) and whatever handler is passed to `start_consuming`. The consumer is created with `enable_auto_commit=False`, and `_run` only calls `consumer.commit()` when the handler returns `CONSUMED` — so a message counts as done only once it's been fully handled (including being resolved to a `DENIED` completion), not merely received. A handler exception that isn't caught internally propagates out of `_run`'s `try` (logged via `logger.exception`, nothing committed), so that message is redelivered on the next poll/restart. `handle_truck_assignment_requested` uses this by catching `UnknownDelivery`/`InvalidCargoWeight`/`NoTruckAvailable` itself and returning `CONSUMED` in all three cases — deterministic business rejections are meant to resolve, not retry forever.

**Producer delivery confirmation:** `aiokafka`'s `AIOKafkaProducer.send()` only confirms the message was queued locally (topic metadata resolved, placed in the batch accumulator) — it returns an `asyncio.Future` that resolves separately once the broker actually acknowledges the write (`send_and_wait` is `future = await send(...); return await future`, which adds a full broker round-trip to the caller). Both `assignment_producer.py` modules (Fleet Service and Delivery Service) stay fire-and-forget on that round-trip — they don't await the future, to avoid adding broker latency to the request path — but do capture it and attach `future.add_done_callback(functools.partial(_log_send_failure, topic, delivery_id))`. `_log_send_failure` reads `future.exception()` (not `.result()`, which would just re-raise inside the callback instead of being observable) and, if not `None`, logs it via `logger.error(..., exc_info=exc)` (not `logger.exception`, since that reads from `sys.exc_info()`, only populated inside an active `except` block). This is visibility only — a genuine broker-level failure (timeout, leader unavailable, etc.) is still lost, just no longer silent; no retry or dead-letter mechanism exists yet.

**Test strategy:**
- `kafka` pytest marker, combined with the existing `unit`/`integration` markers.
- `kafka` + `unit`: mocked `aiokafka` producer/consumer, testing call-shape (correct topic/payload on produce) and message-handling logic (correct status transition on consume) in both services. Runs every time, no external dependency.
- `kafka` + `integration`: round-trip smoke tests against a disposable broker spun up via `testcontainers[kafka]` — not the docker-compose Kafka instance, to keep tests isolated. Fleet Service: `test/assignment/test_assignment_kafka_integration.py` + `test/assignment/conftest.py`. Delivery Service: `test/test_assignment_kafka_integration.py` + `test/conftest.py`. Each fixture is a module-scoped `KafkaContainer` (via `testcontainers.community.kafka`) started `.with_kraft()` (matching how the real docker-compose broker runs) with both topics created explicitly through `aiokafka`'s `AIOKafkaAdminClient`, mirroring `infra/kafka/create_topics.sh`. Tests point `kafka_client.KAFKA_BOOTSTRAP_SERVERS` at the container via `monkeypatch.setattr` (the module reads the env var once at import time, so `monkeypatch.setenv` wouldn't take effect), start the app's real producer/consumer, and assert the expected outcome — either a message arriving on a throwaway consumer, or a repository record updating — polled with `asyncio.wait_for(..., timeout=15)` rather than a fixed sleep. These tests are `async def` using `pytest-asyncio` (`asyncio_mode = "strict"`), unlike the `kafka` + `unit` tests, since round-tripping through a real broker means running a background consumer task concurrently with producing and awaiting the result.
- Running both services' `kafka` + `integration` tests at the same time can be flaky: two Kafka JVM brokers cold-booting concurrently on the same Docker Desktop instance occasionally contend for resources. Run them sequentially (`run-tests.bat`, the documented default) for reliability; if a concurrent run does fail this way, retrying alone usually passes.
- Rationale: verifying Kafka itself works isn't this project's responsibility (the broker health check plus `kafka_init`'s explicit topic creation already cover that); verifying *our* producer/consumer contract with Kafka is.

### Data models
- **Truck:** `id`, `plate_number`, `capacity_kg`, `status` (`AVAILABLE` / `IN_USE` / `IN_REPAIR`)
- **Delivery:** `id`, `client_id`, `pickup_location`, `dropoff_location`, `cargo_weight_kg`, `requested_date`, `status` (`REQUESTED` / `ASSIGNED` / `DENIED` / `COMPLETED`), `assigned_truck_id`, `denial_reason` (Delivery Service's own `DeliveryDenialReason` enum — currently mirrors `TruckAssignmentFailureReason`'s values but is a deliberately separate type, expected to grow values beyond Fleet Service's technical reasons as the product develops), `denial_description` (free-text detail, set only when `status` is `DENIED`)

## Test Conventions

pytest markers (defined identically in each service's own `pyproject.toml` under `[tool.pytest.ini_options]` — see "Running tests" below for why each service needs its own copy):
| Marker | Meaning |
|---|---|
| `unit` | Fast, isolated |
| `integration` | Crosses layers or calls external systems |
| `routes` | FastAPI route behavior (uses `TestClient`) |
| `service` | Service layer business logic |
| `repository` | Repository/storage behavior |
| `kafka` | Kafka producer/consumer behavior |

Route tests use FastAPI `TestClient`. The Kafka producer (`assignment_producer.produce_truck_assignment_requested`/`produce_truck_assignment_completed`) is monkeypatched with an `AsyncMock` in service/route tests. Repository fixtures use `autouse` to reset in-memory state between tests.

**Running tests:** each service has its own local `.venv` (e.g. `apps/delivery_service/.venv`) with `pytest`, `fastapi`, and `aiokafka` installed — the workspace-root `.venv` does not have `pytest` at all, and `uv run pytest` should be avoided (it can implicitly `uv sync` and modify `uv.lock`). Run tests with the service's own interpreter from inside the service directory, e.g. `cd apps/delivery_service && .venv/Scripts/python.exe -m pytest test -q`. Doing it that way picks up the service's own `pyproject.toml` `[tool.pytest.ini_options]` as the config — pytest resolves config per-directory, walking up from wherever it's invoked, and stops at the first `pytest.ini`/`pyproject.toml` it finds. Markers live only in each service's own `pyproject.toml`, kept in sync by hand, since the two services intentionally keep independent venvs/configs rather than sharing one workspace-wide test environment.

**Adding a new test dependency to a service — a uv gotcha:** don't reach for plain `uv add`/`uv sync` from inside a service directory expecting it to update that service's own local `.venv`/`uv.lock` — because each service is declared a member of the root `[tool.uv.workspace]`, uv resolves those commands against the **shared root environment** instead (uv workspaces are single-environment by design; there's no per-command flag to opt out — `--no-workspace` controls something unrelated, whether the dependency *being added* becomes a workspace member). Each service's local `.venv` + its own tracked `uv.lock` isn't wired up to that workspace tooling, so instead: add the dependency to the service's own `pyproject.toml` by hand (or let `uv add` do that part — it does update the right `pyproject.toml` even though it installs to the wrong place — then revert whatever it changed in the root `uv.lock`/`.venv`), and install it directly with `.venv/Scripts/python.exe -m pip install <package>` from inside the service directory.

## Workspace Layout

```
pyproject.toml          # uv workspace root — members: apps/*
run-tests.bat            # runs both services' tests sequentially (see Common Commands) —
                         #   exists because PyCharm compound run configs launch children in
                         #   parallel, which causes Kafka container contention
apps/
  fleet_service/
    app/
      routes/           # truck_routes
      services/         # truck_service, assignment_service
      repositories/     # truck_repository, assignment_repository
      models/           # truck, assignment
      clients/          # kafka_client (aiokafka) — consumer (group_id, manual commit
                         #   via QueueMessageStatus) and producer
      consumers/        # assignment_consumer — Kafka-triggered entry point into
                         #   assignment_service
      producers/        # assignment_producer — produces TruckAssignmentCompleted onto
                         #   truck-assignment-completed
    test/
      assignment/        # test_assignment_repository, test_assignment_service,
                         #   test_assignment_producer, test_assignment_consumer,
                         #   test_assignment_kafka_integration
                         #   (+ conftest.py: the testcontainers KafkaContainer fixture)
      truck/             # test_truck_repository, test_truck_routes, test_truck_service
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
      clients/          # kafka_client (aiokafka, consumer + producer) — this service
                         #   talks to Fleet Service only via Kafka, no HTTP client
      consumers/        # assignment_consumer — handles truck-assignment-completed,
                         #   updates delivery status via delivery_service
      producers/        # assignment_producer — produces TruckAssignmentRequest onto
                         #   truck-assignment-requested
    test/                # test_delivery_repository, test_delivery_routes,
                         #   test_delivery_service, test_assignment_producer,
                         #   test_assignment_consumer, test_assignment_kafka_integration
                         #   (+ conftest.py: the testcontainers KafkaContainer fixture)
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
- Fleet Service: create truck (`POST /trucks`), list trucks (`GET /trucks`), Kafka consumer/producer handling truck assignment requests/completions
- Delivery Service: create delivery (`POST /deliveries`), list deliveries (`GET /deliveries`), get delivery by id (`GET /deliveries/{id}`), Kafka producer/consumer for the truck-assignment flow
- Kafka-based truck assignment implemented end-to-end (see Architecture > Kafka), including producer delivery-confirmation logging and structured error handling on both consumers
- Full pytest coverage across both services: routes, services, repositories, Kafka producers/consumers, and `kafka` + `integration` round-trip tests against disposable brokers
- Structured logging (`logging` module, `LOG_LEVEL` env var) in both services
- Local deployment via Docker Compose (`docker-compose.yml`) and Kubernetes (`infra/k8s/deploy-local.bat` / `shutdown-local.bat`)
- Kafka bootstrap URL externalized (`KAFKA_BOOTSTRAP_SERVERS`, mutualized via a YAML anchor in `docker-compose.yml`) instead of hardcoded per-service

**In progress / Next up:**
- Add persistence for Fleet/Delivery Services (currently in-memory only, lost on restart) and for Kafka (currently no volume, flagged by the `TODO` in `docker-compose.yml`)

**Later:**
- Malformed messages (pydantic `ValidationError`) on both `truck-assignment-requested` and `truck-assignment-completed` are currently logged and committed (i.e. dropped) rather than routed anywhere — whether a dead-letter topic is needed is still open (flagged by `TODO`s in both consumers)
- Monitoring and logging (e.g., Prometheus/Grafana, ELK stack)
