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
Note `integration` isn't Kafka-specific — route tests (`test_truck_routes.py`, `test_delivery_routes.py`, `test_assignment_routes.py`) are marked `integration` too, since they cross layers via `TestClient`, even though they don't touch Docker. To exclude only the `testcontainers`-backed Kafka round-trip tests while keeping those, use `-m "not (kafka and integration)"` instead of `-m "not integration"`.

**Run both services' tests sequentially, from the repo root:**
```bash
./run-tests.bat                                          # full suite, both services
./run-tests.bat -m "not (kafka and integration)"          # skip the Kafka container tests
```
Runs Delivery Service's tests, then Fleet Service's, one after the other, stopping at the first failure; any arguments after the script name are forwarded to both `pytest` invocations. This exists because PyCharm's `CompoundRunConfigurationType` (used for a "run everything" run configuration) always launches its child configurations **simultaneously**, not sequentially, and there's no setting to change that — running both services' `kafka` + `integration` tests at the same time causes real flakiness (see Test Conventions), so the compound approach was replaced with this script for anyone wiring up a single "run all tests" PyCharm configuration (as a Batch run configuration pointed at this script instead of a compound one).

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
Manages deliveries. Same layer structure, plus Kafka producer/consumer clients for talking to Fleet Service asynchronously (see Architecture > Kafka).
- `POST /deliveries`, `GET /deliveries`, `GET /deliveries/{id}`
- On delivery creation, it produces a truck-assignment request onto Kafka and returns immediately with status `REQUESTED`; the eventual `ASSIGNED`/`DENIED` outcome arrives via a Kafka consumer and is only visible on a later `GET /deliveries/{id}`.

### Inter-service communication
Truck assignment used to go through a synchronous HTTP call — `delivery_service/app/clients/fleet_client.py` (`httpx`, async) calling Fleet Service's `POST /internal/truck-assignments`, base URL from the `FLEET_SERVICE_URL` env var. That module (and the `except TimeoutException` handling in `delivery_routes.py` that went with it) has been removed now that `create_delivery` produces to Kafka instead (see Architecture > Kafka below) — the internal HTTP route itself (`POST /internal/truck-assignments`) is still there on the Fleet Service side, kept temporarily for manual testing (see "Fate of `/internal/truck-assignments`" below).

### Kafka
A single-node broker (`confluentinc/cp-kafka`, KRaft mode — no Zookeeper) runs as the `kafka` service in `docker-compose.yml`, with a combined `broker,controller` role. It exposes three listeners: `CLIENT` (`kafka:9092`, for other containers — used by `fleet_service`, `delivery_service`, `kafka_init`, `redpanda_console`), `EXTERNAL` (published to the host as `localhost:9094`, so non-containerized local runs, e.g. plain `uvicorn`, can reach the broker too — Kafka's advertised-listener metadata means a single listener can't correctly serve both container and host clients), and `CONTROLLER` for KRaft's internal Raft consensus.

Topics are created explicitly and automatically on startup by a one-shot `kafka_init` service, which runs `infra/kafka/create_topics.sh` (a POSIX `sh` script, idempotent via `--if-not-exists`) once `kafka` reports healthy, then exits. Both app services `depends_on` both `kafka` (`condition: service_healthy`) and `kafka_init` (`condition: service_completed_successfully`), so they don't start until the broker is up and topics exist.

Topics defined so far (1 partition, replication factor 1 — single-broker local setup):
- `truck-assignment-requested` — intended: Delivery Service produces, Fleet Service consumes
- `truck-assignment-completed` — intended: Fleet Service produces, Delivery Service consumes

Both topics are now produced and consumed end-to-end by application code: `truck-assignment-requested` is produced by Delivery Service and consumed by Fleet Service; `truck-assignment-completed` is produced by Fleet Service and consumed by Delivery Service.

A `redpanda_console` service (Redpanda Console, image `docker.redpanda.com/redpandadata/console`) is also in `docker-compose.yml`, giving a web UI at `http://localhost:8080` for browsing topics/messages and consumer groups on the local broker. It connects to `kafka:9092` and waits on the same `kafka` (healthy) / `kafka_init` (completed) conditions as the app services.

### Kafka-based truck assignment

Assignment has moved off the synchronous `fleet_client` HTTP call onto the two existing topics; all four flow steps below are implemented end-to-end, and the dead `fleet_client.py` / `except TimeoutException` cleanup is done too — see Project Status for exact state.

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

**Producer delivery confirmation (currently a gap):** `aiokafka`'s `AIOKafkaProducer.send()` only awaits topic-metadata resolution and placing the message into the local batch accumulator; it returns an `asyncio.Future` that resolves separately once the broker actually acknowledges the write (that's what `send_and_wait` awaits on top: `future = await send(...); return await future`). Both `assignment_producer.py` modules (Fleet Service and Delivery Service) currently do `await get_producer().send(...)` and discard that returned future — so a broker-level failure *after* the message is queued (timeout, leader unavailable, etc.) is never observed by our code; `aiokafka` just logs "exception was never retrieved." For Delivery Service specifically, this means a `create_delivery` call could return `201`/`REQUESTED` while the actual produce silently fails, leaving the delivery stuck in `REQUESTED` forever with no error anywhere. This is the concrete shape of the still-open "producer error handling isn't designed yet" item below — the fix is either `send_and_wait` (confirms delivery before returning, adds real broker round-trip latency to the request) or fire-and-forget via `asyncio.create_task` with an explicit callback that handles the future's eventual exception.

**Fate of `/internal/truck-assignments`:** likely retired once the consumer-based flow is live; may be kept temporarily for manual testing during the transition.

**Test strategy:**
- New `kafka` pytest marker, combined with the existing `unit`/`integration` markers.
- `kafka` + `unit`: mocked `aiokafka` producer/consumer, testing call-shape (correct topic/payload on produce) and message-handling logic (correct status transition on consume) in both services. Runs every time, no external dependency.
- `kafka` + `integration`: a small number of true round-trip smoke tests against a disposable broker spun up via `testcontainers[kafka]` — not the docker-compose Kafka instance, to keep tests isolated and not dependent on the stack already being up. Fleet Service has one so far (`test/assignment/test_assignment_kafka_integration.py`): a module-scoped `kafka_bootstrap_servers` fixture (`test/assignment/conftest.py`) starts a `KafkaContainer` (via `testcontainers.community.kafka`, the non-deprecated location — plain `testcontainers.kafka` now warns) and explicitly creates both topics through `aiokafka`'s own `AIOKafkaAdminClient`, mirroring `infra/kafka/create_topics.sh`'s partitions/replication rather than relying on Kafka's default auto-topic-creation. The container is started with `.with_kraft()` — `KafkaContainer`'s default is a legacy single-container Zookeeper-mode boot, which crashed on startup (exit code 1) on a repeat run despite passing once; KRaft mode is both the fix (reliable, no embedded-ZK boot script) and the more correct choice anyway, since it matches how the real docker-compose broker actually runs (see Architecture > Kafka). The test itself points `kafka_client.KAFKA_BOOTSTRAP_SERVERS` at the container (via `monkeypatch.setattr` on the module attribute, not `monkeypatch.setenv` — the module reads the env var once at import time into that constant, so only patching the attribute directly actually takes effect), starts the app's real producer/consumer, produces a raw `truck-assignment-requested` message with a throwaway `aiokafka` producer, and asserts the expected `truck-assignment-completed` message arrives on a throwaway consumer (awaited via `asyncio.wait_for(..., timeout=15)` rather than a fixed sleep, to avoid flakiness). Delivery Service now has the mirror-image test (`test/test_assignment_kafka_integration.py`, `test/conftest.py`): same `KafkaContainer().with_kraft()` fixture, but since Delivery Service's consumer only has a repository side effect (no further topic to produce to), the test seeds a `REQUESTED` delivery via `delivery_repository.save(...)`, produces a raw `truck-assignment-completed` message with a throwaway producer, and polls `delivery_repository.get_delivery_by_id(...)` in a tight loop (`await asyncio.sleep(0.1)` between checks) wrapped in the same `asyncio.wait_for(..., timeout=15)` — the poll-with-timeout principle applied where there's no output topic to `getone()` from. Both services hit the identical hatchling/uv-workspace dependency-install gotcha (see Test Conventions) when adding `testcontainers[kafka]`/`pytest-asyncio`, and both crashed once on Zookeeper-mode before `.with_kraft()` was applied — for Delivery Service `.with_kraft()` was included from the start, so it only hit an unrelated one-off Docker Desktop teardown flake (`could not kill container: tried to kill container, but did not receive an exit event`, after the test itself had already passed) — not reproduced on 2 subsequent clean runs, treated as Docker Desktop/npipe flakiness rather than a code issue.
- **Running both services' `kafka` + `integration` tests at the same time is flaky.** Each service's fixture starts its own independent `KafkaContainer` (confirmed via distinct container IDs — they are *not* sharing a broker), but two full Kafka JVM brokers cold-booting at the same moment on the same Docker Desktop instance occasionally lose the race: observed exit code 139 (SIGSEGV) once and exit code 1 (no useful log) on other runs, non-deterministically, on whichever service's container happened to start second. As mitigation, both `conftest.py` fixtures now set `KAFKA_HEAP_OPTS=-Xmx512m -Xms512m` on the container (`KafkaContainer().with_kraft().with_env("KAFKA_HEAP_OPTS", "-Xmx512m -Xms512m")`) to shrink each broker's memory footprint — this did **not** fully eliminate the flakiness in testing (a concurrent run still failed once afterward with the same exit-code-1 signature), so the contention looks more like CPU/scheduling pressure during the simultaneous `kafka-storage format` + broker-boot step than pure memory sizing. Practically: run the two services' suites sequentially (the normal, documented way) rather than simultaneously; if a concurrent/parallel run does fail this way, it's very likely this contention, not a real bug — retrying it alone usually passes. Separately, a stuck container from an earlier unrelated teardown flake (`could not kill container: tried to kill container, but did not receive an exit event` — a Docker Desktop-level bug, not fixable via `docker rm -f`/`docker kill` from the CLI) was found still running 18+ minutes later, still holding a host port, and was very likely making the contention worse; restarting Docker Desktop cleared it and a subsequent concurrent run passed cleanly. If concurrent runs ever get mysteriously flaky again, check `docker ps -a` for a container stuck in that state before assuming it's a test bug.
- These tests are written as `async def test_...` functions using `pytest-asyncio` (`@pytest.mark.asyncio`, `asyncio_mode = "strict"` in `pyproject.toml`) rather than the `asyncio.run(...)`-in-a-sync-`def` style the existing `kafka` + `unit` tests use — round-tripping through a real broker means running a background consumer task concurrently with producing and then awaiting the result, which reads far more naturally as native `async def` than one big `asyncio.run(main())` wrapper. The existing unit tests haven't been migrated to `pytest-asyncio` (deliberately out of scope for now); if the pattern proves out, migrating them is a likely follow-up.
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

Route tests use FastAPI `TestClient`. The Kafka producer (`assignment_producer.produce_truck_assignment_requested`/`produce_truck_assignment_completed`) is monkeypatched with an `AsyncMock` in service/route tests, same role `fleet_client` used to play before it was removed. Repository fixtures use `autouse` to reset in-memory state between tests.

**Running tests:** each service has its own local `.venv` (e.g. `apps/delivery_service/.venv`) with `pytest`, `fastapi`, and `aiokafka` installed — the workspace-root `.venv` does not have `pytest` at all, and `uv run pytest` should be avoided (it can implicitly `uv sync` and modify `uv.lock`). Run tests with the service's own interpreter from inside the service directory, e.g. `cd apps/delivery_service && .venv/Scripts/python.exe -m pytest test -q`. Doing it that way picks up the service's own `pyproject.toml` `[tool.pytest.ini_options]` as the config — pytest resolves config per-directory, walking up from wherever it's invoked, and stops at the first `pytest.ini`/`pyproject.toml` it finds, so each service's config is self-contained and markers must be declared there directly rather than in one shared root file. There used to be a root `pytest.ini` with the marker declarations, but it was silently unused by this workflow (never reached, since each service's own `pyproject.toml` is found first) and has been removed; markers now live only in each service's `pyproject.toml`, kept in sync by hand since the two services intentionally keep independent venvs/configs rather than sharing one workspace-wide test environment.

**Adding a new test dependency to a service — another uv gotcha:** don't reach for plain `uv add`/`uv sync` from inside a service directory expecting it to update that service's own local `.venv`/`uv.lock` — because each service is declared a member of the root `[tool.uv.workspace]`, uv resolves those commands against the **shared root environment** instead (uv workspaces are single-environment by design; there's no per-command flag to opt out — `--no-workspace` controls something unrelated, whether the dependency *being added* becomes a workspace member). Each service's local `.venv` + its own tracked `uv.lock` isn't actually wired up to that workspace tooling, so instead: add the dependency to the service's own `pyproject.toml` by hand (or let `uv add` do that part — it does update the right `pyproject.toml` even though it installs to the wrong place — then revert whatever it changed in the root `uv.lock`/`.venv`), and install it directly with `.venv/Scripts/python.exe -m pip install <package>` from inside the service directory. Hit and worked around once already adding `testcontainers[kafka]`/`pytest-asyncio` to Fleet Service — see Project Status.

## Workspace Layout

```
pyproject.toml          # uv workspace root — members: apps/*
run-tests.bat            # runs both services' tests sequentially (see Common Commands) —
                         #   exists because PyCharm compound run configs launch children in
                         #   parallel, which causes Kafka container contention
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
      assignment/        # test_assignment_repository, test_assignment_routes,
                         #   test_assignment_service, test_assignment_producer,
                         #   test_assignment_consumer, test_assignment_kafka_integration
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
      clients/          # kafka_client (aiokafka, consumer + producer) — fleet_client
                         #   (httpx) has been removed, this service is Kafka-only now
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
- Removed the now-dead synchronous HTTP path: `delivery_service/app/clients/fleet_client.py` deleted, and the stale `except TimeoutException` handling in `delivery_routes.py` (which was already gone) along with the now-unused `from httpx import TimeoutException` import
- `delivery_service` test suite rewritten for the Kafka-based flow — `test_delivery_service.py` and `test_delivery_routes.py` now mock `assignment_producer.produce_truck_assignment_requested` and assert `create_delivery`/`POST /deliveries` return status `REQUESTED` immediately (previously asserted the old synchronous `ASSIGNED`/`DENIED`); `test_delivery_service.py` gained a `TestUpdateDeliveryWithTruckAssignment` class covering the assigned/denied/unknown-delivery cases that `update_delivery_with_truck_assignment` now owns. Also fixed a pre-existing bug in the 404 route test (`/delivery/fake_id` typo → `/deliveries/fake_id`, which was passing for the wrong reason)
- Tests for both services' Kafka producer/consumer paths written: `test_assignment_producer.py` (call-shape: correct topic/key/payload) and `test_assignment_consumer.py` (message-handling: success + each failure-reason mapping + malformed-message handling) exist for both Fleet Service (`apps/fleet_service/test/assignment/`) and Delivery Service (`apps/delivery_service/test/`)
- Pytest markers fixed: the `kafka` marker is now registered (alongside the existing five), and markers are declared directly in each service's own `pyproject.toml` `[tool.pytest.ini_options]` rather than the old root `pytest.ini`, which was silently unused by the documented run-from-inside-service-directory workflow and has been deleted — see Test Conventions for why config is per-service. Considered (and rejected for now) switching to a single shared root venv via the `uv.workspace` declaration, which would allow one pytest invocation/PyCharm config across all services with auto-discovery of future ones; deliberately keeping isolated per-service venvs/configs instead, so markers are kept in sync by hand across the two `pyproject.toml` files
- First `kafka` + `integration` test written, for Fleet Service — see Test Conventions for the fixture/test design. Along the way: fixed a pre-existing gap in `fleet_service/pyproject.toml` (missing `[tool.hatch.build.targets.wheel] packages = ["app"]`, which made any `uv add`/`uv sync`-triggered rebuild of the local editable package fail with "Unable to determine which files to ship inside the wheel"), and discovered that `uv add`/`uv sync` run from inside a workspace-member service directory resolve against the **shared root environment** (root `.venv`/`uv.lock`), not that service's own local `.venv`/`uv.lock` — uv workspaces are single-environment by design, and there's no flag to opt a member out of that per-command (`--no-workspace` controls something unrelated: whether the *dependency being added* becomes a workspace member). Each service's local `.venv` + its own tracked `uv.lock` therefore isn't actually wired up to uv's workspace tooling — it must have been bootstrapped independently (matching the `pip install -e .` alternative in Common Commands) — so `testcontainers[kafka]` and `pytest-asyncio` were added to `fleet_service/pyproject.toml`'s `[dependency-groups] dev` (for documentation) and then installed directly via `.venv/Scripts/python.exe -m pip install "testcontainers[kafka]" pytest-asyncio` into the local venv, bypassing `uv add` as the install mechanism.
- Delivery Service's mirror-image `kafka` + `integration` test written too — see Test Conventions for the fixture/test design. Hit the identical hatchling gap and the identical uv-workspace install gotcha (both fixed/worked around the same way as Fleet Service's), and the container fixture was written with `.with_kraft()` from the start this time, avoiding the Zookeeper-mode crash Fleet Service's first version hit.
- Investigated flaky failures when running both services' `kafka` + `integration` tests at the same time — see Test Conventions for the full writeup. Root cause: resource contention between two concurrently-booting Kafka JVM brokers (not a shared-container bug — each service's fixture genuinely gets its own container), worsened on one occasion by a container stuck in a Docker Desktop kill-bug state from an earlier unrelated flake. `KAFKA_HEAP_OPTS=-Xmx512m -Xms512m` was added to both `conftest.py` fixtures to reduce each broker's memory footprint; this helps but did not fully eliminate the flakiness in testing, so running both suites' `kafka` + `integration` tests concurrently should still be expected to occasionally need a retry — running them sequentially (the normal way) remains reliable.
- Added `run-tests.bat` (repo root) to run both services' tests sequentially from a single PyCharm run configuration or command — see Common Commands. Motivated directly by the item above: PyCharm's `CompoundRunConfigurationType` (what a "Run tests" configuration bundling both services uses) always launches its child configurations simultaneously, with no setting to make it sequential instead, so a compound config was exactly what caused the concurrent Kafka contention in the first place. The script forwards any arguments through to both `pytest` invocations, so the same script backs both a full-suite PyCharm configuration and a filtered one (e.g. `-m "not (kafka and integration)"` to skip just the Kafka container tests — see Common Commands for why that's not the same as `-m "not integration"`, since route tests are marked `integration` too without needing Docker).

**In progress / Next up:**
- Malformed messages (pydantic `ValidationError`) on both `truck-assignment-requested` and `truck-assignment-completed` are currently logged and committed (i.e. dropped) rather than routed anywhere — whether a dead-letter topic is needed is still open (flagged by `TODO`s in both consumers)
- Delivery Service (and Fleet Service) Kafka producer error handling isn't designed yet: both `assignment_producer.py` modules `await get_producer().send(...)` and discard the returned future, so a broker-level failure after the message is queued is currently silent — see "Producer delivery confirmation" under Architecture > Kafka for the concrete mechanism and the two candidate fixes (`send_and_wait` vs. fire-and-forget with an explicit error callback)
- Externalize the Kafka URL in `infra/kafka/create_topics.sh` via an env var instead of the hardcoded `kafka:9092` (already flagged by a `TODO` in the script)
- Add persistence for Fleet/Delivery Services (currently in-memory only, lost on restart) and for Kafka (currently no volume, flagged by the `TODO` in `docker-compose.yml`)

**Later:**
- Monitoring and logging (e.g., Prometheus/Grafana, ELK stack)