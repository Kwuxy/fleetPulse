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
Note `integration` isn't Kafka-specific — repository tests (`test_truck_repository.py`, `test_assignment_repository.py`, `test_delivery_repository.py`) are `integration` too, backed by a real Postgres via `testcontainers[postgresql]` (see Test Conventions). At this point `integration` effectively means "needs Docker" project-wide — route tests moved the other way and are `unit` now (mocked service layer, no DB, no Docker; see Test Conventions for why that plan changed from the original one). To exclude only the slower/flakier `testcontainers`-backed Kafka broker round-trip tests while still running the (Postgres-backed) repository tests, use `-m "not (kafka and integration)"` instead of the broader `-m "not integration"`.

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
A single-node broker (`confluentinc/cp-kafka`, KRaft mode — no Zookeeper) runs as the `kafka` service, with a combined `broker,controller` role and three listeners: `CLIENT` (`kafka:9092`, for other containers), `EXTERNAL` (published to the host as `localhost:9094`, so non-containerized local runs like plain `uvicorn` can reach the broker too — Kafka's advertised-listener metadata means one listener can't serve both), and `CONTROLLER` for KRaft's Raft consensus. The `kafka:9092` value is defined once via a YAML anchor (`x-kafka-bootstrap: &kafka-bootstrap kafka:9092` in `docker-compose.yml`) and referenced (`*kafka-bootstrap`) from every service that needs it, instead of repeating the literal four times.

Topics are created explicitly by a one-shot `kafka_init` service, which runs `infra/kafka/create_topics.sh` (a POSIX `sh` script, idempotent via `--if-not-exists`) once `kafka` reports healthy, then exits. The script reads its bootstrap URL from `KAFKA_BOOTSTRAP_SERVERS` (`KAFKA_URL="${KAFKA_BOOTSTRAP_SERVERS:-kafka:9092}"`), which `kafka_init` gets from the anchor above. Both app services `depends_on` both `kafka` (`condition: service_healthy`) and `kafka_init` (`condition: service_completed_successfully`), so they don't start until the broker is up and topics exist.

Topics (1 partition, replication factor 1 — single-broker local setup):
- `truck-assignment-requested` — produced by Delivery Service, consumed by Fleet Service
- `truck-assignment-completed` — produced by Fleet Service, consumed by Delivery Service

A `redpanda_console` service (Redpanda Console, image `docker.redpanda.com/redpandadata/console`) is also in `docker-compose.yml`, giving a web UI at `http://localhost:8080` for browsing topics/messages and consumer groups on the local broker. It connects to `kafka:9092` and waits on the same `kafka` (healthy) / `kafka_init` (completed) conditions as the app services.

### Postgres

A shared `postgres` container (`postgres:18.6-bookworm`) provides the database for both services — one container, two logical databases (`fleet_service`, `delivery_service`), each with its own restricted user, mirroring the Kafka pattern above. Data persists in a named volume (`postgres_data`), mounted at `/var/lib/postgresql` rather than `.../data` — Postgres 18+ manages a version-specific data subdirectory itself under a single parent mount (this is what enables `pg_upgrade --link`); mounting straight onto the old `.../data` path throws a startup error on 18+ ("configured to store database data in a format which is compatible with pg_ctlcluster").

Credentials come from a git-ignored `.env` file at the repo root (`POSTGRES_ADMIN_USER/PASSWORD`, shared `POSTGRES_HOST/PORT`, and per-service `FLEET_SERVICE_DB_USER/PASSWORD/NAME` / `DELIVERY_SERVICE_DB_*` triples), interpolated into `docker-compose.yml`. Each app service's `environment:` block aliases its own triple onto the generic `POSTGRES_HOST/PORT/DB/USER/PASSWORD` names — the shape `db_client.py` and each service's `migrations/env.py` read from `os.environ`, with `POSTGRES_HOST` defaulting to `localhost` (mirroring `kafka_client.py`'s `KAFKA_BOOTSTRAP_SERVERS` default) so local tools work without Docker. `postgres` also publishes `5432:5432` to the host for the same reason as Kafka's `EXTERNAL` listener. The env file must be named exactly `.env` at the repo root — Compose only auto-loads that name. `POSTGRES_USER`/`PASSWORD` on the `postgres` service itself just bootstrap its own admin superuser (`fleetpulse_admin`) on first boot; that's not what the app services connect with at runtime.

Per-service databases/users are bootstrapped by a `postgres_init` one-shot service (`infra/postgres/init-databases.sh`), not the Postgres image's `/docker-entrypoint-initdb.d/` hook — that only fires once, on a container's first boot, so a later service's database would be silently skipped against an already-initialized volume. `postgres_init` instead runs on every `docker compose up`, guarding each `CREATE DATABASE`/`CREATE USER` with an existence check (Postgres has no native `IF NOT EXISTS` for either), so it's safe to re-run — a future service's DB/user is just another call to the script's `create_db_and_user` function. Both app services `depends_on` `postgres` (healthy) and `postgres_init` (completed), same shape as their Kafka dependencies.

**psql `-c` quirk:** colon-style variable interpolation (`:'var'`, used to embed each per-service password into `CREATE USER ... WITH PASSWORD :'pass'` without hand-splicing it into raw SQL) only works for SQL read via `-f` or piped over stdin — not a one-shot `-c "..."` argument, which sends the text verbatim and errors on the bare `:`. `init-databases.sh` pipes that one statement through stdin for this reason; its other statements (existence checks, `CREATE DATABASE`, `GRANT`) don't interpolate anything and stay on `-c`.

**Postgres 15+ schema-privilege gotcha:** Postgres 15 revoked `CREATE` on the `public` schema from the implicit `PUBLIC` role every user used to inherit it from, so `create_db_and_user` also runs `GRANT ALL ON SCHEMA public TO ...` per database, alongside the database-level grant — without it, a service's first Alembic migration fails with `permission denied for schema public`.

### Alembic migrations

Each service's `migrations/env.py` builds its own SQLAlchemy `URL` from the same five `POSTGRES_*` env vars `db_client.py` reads. Running Alembic locally (outside Docker — e.g. `alembic revision --autogenerate`, `alembic upgrade head`) surfaced several gotchas that `docker compose up` never hits, since nothing auto-loads the root `.env` outside of Compose:

- **`.env` loading:** `env.py` reads `.env` via `dotenv_values()`, not `load_dotenv()` — the latter would also import `.env`'s `POSTGRES_HOST=postgres` (the docker-network hostname) into the process, defeating `db_client.py`'s `localhost` default meant for local-without-Docker runs. Only the per-service `*_DB_USER/PASSWORD/NAME` values are pulled from the loaded dict and aliased onto the generic `POSTGRES_USER/PASSWORD/DB` names, duplicated by hand per service same as everywhere else in this project.
- **`str(url)` masks the password:** SQLAlchemy's `URL.__str__` always renders it as `***` (a 1.4+ safety default) — passing that to `config.set_main_option('sqlalchemy.url', ...)` would silently authenticate with the literal string `***`. Use `sqlalchemy_url.render_as_string(hide_password=False)` instead.
- **`ConfigParser` and `%`:** Alembic's `Config` stores `sqlalchemy.url` in a `ConfigParser`, which treats `%` as its own interpolation marker — a percent-encoded password (e.g. `%5E` for `^`) raises `ValueError: invalid interpolation syntax` when read back out. `run_async_migrations()` sidesteps this (and the masking gotcha above) by building the engine directly from the `URL` object rather than round-tripping it through `config` as a string.
- **`target_metadata` needs the ORM model imported, not just `Base`:** a table only registers on `Base.metadata` once the module defining it actually runs, so `env.py` imports the service's ORM model module (e.g. `app.models.orm.delivery`) before capturing `target_metadata` — skip it and `--autogenerate` silently produces an empty diff.
- **A literal `$` in a `.env` password breaks Docker Compose, not Python:** Compose's `${VAR}` interpolation treats `$X` in a `.env` value as a reference to another variable and blanks it if `X` is undefined, while `dotenv_values()` reads the same file literally — the two disagree on what the password actually is. Avoid `$` in generated passwords, or escape as `$$`.
- **Revision IDs stay Alembic's default random hash**, not hand-rolled sequential numbers — each service's `migrations/versions/` and `alembic_version` table are already fully independent (separate databases), so there's no cross-service ordering a sequential scheme would help with.

Creating a migration: `.venv/Scripts/python.exe -m alembic revision --autogenerate -m "<message>"` from inside the service directory, same interpreter convention as tests.

Applying a migration: `.venv/Scripts/python.exe -m alembic upgrade head` from inside the service directory, same interpreter convention as tests.

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

"Redelivered on the next poll/restart" means what it says literally, not "the next poll of a still-running consumer": a message's in-memory fetch position advances the moment it's handed to the handler, commit or not, so a live consumer session never re-fetches something it already yielded. Redelivery only happens once a *new* session joins the group — an actual restart or rebalance — and resumes from the last committed offset. For that to work correctly even when there's no committed offset yet (a brand-new consumer group, or a restart before anything's ever been committed), the consumer is also created with `auto_offset_reset="earliest"` — not aiokafka's own default of `"latest"`, which would instead resume from "whatever's newest right now" and silently skip everything already queued, including the very message that just failed. This was found while building the `kafka` + `integration` redelivery test below; see that section for how it was diagnosed.

**Producer delivery confirmation:** `aiokafka`'s `AIOKafkaProducer.send()` only confirms the message was queued locally (topic metadata resolved, placed in the batch accumulator) — it returns an `asyncio.Future` that resolves separately once the broker actually acknowledges the write (`send_and_wait` is `future = await send(...); return await future`, which adds a full broker round-trip to the caller). Both `assignment_producer.py` modules (Fleet Service and Delivery Service) stay fire-and-forget on that round-trip — they don't await the future, to avoid adding broker latency to the request path — but do capture it and attach `future.add_done_callback(functools.partial(_log_send_failure, topic, delivery_id))`. `_log_send_failure` reads `future.exception()` (not `.result()`, which would just re-raise inside the callback instead of being observable) and, if not `None`, logs it via `logger.error(..., exc_info=exc)` (not `logger.exception`, since that reads from `sys.exc_info()`, only populated inside an active `except` block). This is visibility only — a genuine broker-level failure (timeout, leader unavailable, etc.) is still lost, just no longer silent; no retry or dead-letter mechanism exists yet.

**Test strategy:**
- `kafka` pytest marker, combined with the existing `unit`/`integration` markers.
- `kafka` + `unit`: mocked `aiokafka` producer/consumer, testing call-shape (correct topic/payload on produce) and message-handling logic (correct status transition on consume) in both services. Runs every time, no external dependency.
- `kafka` + `integration`: round-trip smoke tests against a disposable broker spun up via `testcontainers[kafka]` — not the docker-compose Kafka instance, to keep tests isolated. Fleet Service: `test/assignment/test_assignment_kafka_integration.py` + `test/assignment/conftest.py`. Delivery Service: `test/test_assignment_kafka_integration.py` + `test/conftest.py`. Each fixture is a module-scoped `KafkaContainer` (via `testcontainers.community.kafka`) started `.with_kraft()` (matching how the real docker-compose broker runs) with both topics created explicitly through `aiokafka`'s `AIOKafkaAdminClient`, mirroring `infra/kafka/create_topics.sh`. Tests point `kafka_client.KAFKA_BOOTSTRAP_SERVERS` at the container via `monkeypatch.setattr` (the module reads the env var once at import time, so `monkeypatch.setenv` wouldn't take effect), start the app's real producer/consumer, and assert the expected outcome — either a message arriving on a throwaway consumer, or a repository record updating — polled with `asyncio.wait_for(..., timeout=15)` rather than a fixed sleep. These tests are `async def` using `pytest-asyncio` (`asyncio_mode = "strict"`), unlike the `kafka` + `unit` tests, since round-tripping through a real broker means running a background consumer task concurrently with producing and awaiting the result.
- Running both services' `kafka` + `integration` tests at the same time can be flaky: two Kafka JVM brokers cold-booting concurrently on the same Docker Desktop instance occasionally contend for resources. Run them sequentially (`run-tests.bat`, the documented default) for reliability; if a concurrent run does fail this way, retrying alone usually passes.
- Rationale: verifying Kafka itself works isn't this project's responsibility (the broker health check plus `kafka_init`'s explicit topic creation already cover that); verifying *our* producer/consumer contract with Kafka is.
- **Both services' `kafka` + `integration` suites were redesigned to mock the service layer**, instead of seeding a real truck/delivery through the real repository — that coverage now belongs to the repository tests (see Test Conventions). Each suite mocks its own service call (`assignment_service.assign_truck_to_delivery` in Fleet, `delivery_service.update_delivery_with_truck_assignment` in Delivery) and tests purely the Kafka contract: real broker (via `testcontainers`), real serialization, real consumer/producer wiring, no DB.
  - **Fleet** (`test/assignment/test_assignment_kafka_integration.py`, `TestAssignmentKafkaIntegration`, 7 cases): successful assignment produces the right completed message on the real broker; `UnknownDelivery`/`InvalidCargoWeight`/`NoTruckAvailable` each map to the right `DENIED` reason (`INVALID_REQUEST` / `NO_AVAILABLE_TRUCK`); an uncaught `RuntimeError` gets the message redelivered after a forced consumer restart; a *successful* handling does not get redelivered after that same forced restart; a malformed request message is dropped without the service ever being called.
  - **Delivery** (`test/test_assignment_kafka_integration.py`, `TestDeliveryKafkaIntegration`, 5 cases): same shape, minus the two-reason split — `handle_truck_assignment_completed` only ever catches one exception, `NotFoundException`, since a *completed* message was already validated on Fleet's side. Delivery's consumer also produces nothing in response, so every test here polls the mocked service call directly instead of an output topic.
  - Fixture pattern in both: an `autouse` pair — `mock_kafka_bootstrap_servers` (points `kafka_client.KAFKA_BOOTSTRAP_SERVERS` at the test container) and `running_assignment_consumer_and_producer` (starts/stops the app's real producer + consumer around each test) — plus explicit `kafka_consumer`/`kafka_producer` fixtures for injecting/observing raw messages where a test still needs to. Fleet splits these across `test/conftest.py` (shared `postgres_db`) and `test/assignment/conftest.py` (Kafka-specific); Delivery keeps everything in one `test/conftest.py`, since it has no `assignment/` subdirectory.
  - Forcing redelivery requires an actual restart (`kafka_client.stop_consuming()` + `start_consuming()`) — a live consumer session never re-fetches a message it already yielded, commit or not (see Offset commit contract above). Both services hit the same missing-`auto_offset_reset` gap independently while building these tests: without `auto_offset_reset="earliest"`, a restarted consumer with no prior committed offset for the group falls back to `aiokafka`'s own `"latest"` default and skips straight past the very message it should be redelivering. Fleet's `kafka_client.py` was fixed first; Delivery's had the identical gap, never carried over, and only surfaced once Delivery got its own forced-restart test.
  - General test-design takeaway: poll a concrete condition for a *positive* outcome (a mock's `await_count`, a message arriving) rather than sleeping a fixed duration; a fixed sleep is the right tool only for proving a *negative* ("nothing else happened"), since there's no condition to poll toward.

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

Route tests use FastAPI `TestClient`. The Kafka producer (`assignment_producer.produce_truck_assignment_requested`/`produce_truck_assignment_completed`) is monkeypatched with an `AsyncMock` in service/route tests.

**Service-layer test convention:** mock the repository module's functions with `AsyncMock` via `monkeypatch.setattr(the_repository_module, "function_name", mock)` — patched on the module object, since that's where the service module looks the name up at call time (it imports the module, e.g. `from app.repositories import truck_repository`, not the bare function name — patching a bare-name import instead would silently miss, since the service would still be holding its own reference to the original function). Fixtures providing these mocks are scoped to the nested test class that actually needs them (e.g. `mock_produce_truck_assignment_requested` only exists on `TestCreateDelivery`, not sibling classes in the same file) rather than one blanket autouse fixture per module — a fixture defined on an outer test class is visible to its nested inner classes, so a mock shared by two of three nested classes only needs to be defined once, on the outer class, without `autouse`. Mock assertions should verify the actual behavioral contract a test is proving (e.g. an invalid-input test asserts the repository's save function was never awaited), not every collaborator that merely isn't reached under today's implementation order — asserting on an incidental, unrelated non-call makes the test fail on a harmless future reorder of unrelated validation checks.

**Repository test convention (Postgres-backed, done):** the old pattern — an `autouse` fixture calling a synchronous in-memory `clear()` between tests — no longer applies now that repositories are Postgres-backed. Repository tests (`test_truck_repository.py`, `test_assignment_repository.py`, `test_delivery_repository.py`) are `repository` + `integration`, backed by a real, disposable Postgres via `testcontainers[postgresql]` (specifically `testcontainers.community.postgres.PostgresContainer` — the base `testcontainers` package already includes it, no extra dependency needed, since Postgres readiness is checked via `psql` inside the container rather than a Python driver). The pattern, defined once per service in a module-scoped `postgres_db` fixture in `test/conftest.py`:
- Start the container with `driver="asyncpg"`, build a `sqlalchemy.engine.URL` from its connection details, and monkeypatch `db_client._build_database_url` directly to return it — not environment variables — since `db_client.py` only reads `os.environ` inside that one function.
- Create the schema with `Base.metadata.create_all` via a throwaway engine rather than running real Alembic migrations — deliberately simpler and faster for tests, at the cost of never exercising the migration files themselves through this path.
- Call the real `db_client.start_db()` so every repository call under test goes through the actual `get_session()`/`async_sessionmaker` code path.
- A separate, function-scoped `clear_repository` fixture (depending on `postgres_db` to guarantee ordering) awaits the repository's own `clear()` before every test, so the container/engine/event loop are shared for the whole module but table state isn't.

**Event-loop gotcha hit building this:** `asyncpg` connections are bound to the event loop they were created on. An early version ran the fixture's setup through its own throwaway `asyncio.run(...)` call, separate from whatever loop `pytest-asyncio` hands each test — the second test then failed deep inside `asyncpg` with a cryptic Windows `ProactorEventLoop` `AttributeError: 'NoneType' object has no attribute 'send'`, since its connection was still bound to the first test's already-closed loop. Fix: make `postgres_db` a real `pytest_asyncio.fixture` and pin everything to one shared loop — the fixture, the `clear_repository` fixture, and the test class all declare `loop_scope="module"` (`@pytest_asyncio.fixture(scope="module", loop_scope="module")`, `@pytest_asyncio.fixture(autouse=True, loop_scope="module")`, `@pytest.mark.asyncio(loop_scope="module")`).

**Route test convention (done, reversed from an earlier plan):** routes stay `routes` + `unit`, mocking the service layer (`truck_service`/`delivery_service`) entirely — not `integration` backed by testcontainers as originally planned (see Project Status history). No `postgres_db` fixture, no `db_client`, no real Kafka; tests are plain sync functions again since `TestClient` handles the async route internally. Reasoning: `TestClient(app)` used without `with` (the pattern every route test file uses) never triggers the app's `lifespan` — confirmed by running a route test against a stale, unmocked repository call and seeing `RuntimeError: DB engine is not started` — and both services' `lifespan` starts a real Kafka consumer *and* the real DB together. Opting into `with TestClient(app) as client:` to get a "fully real" app would therefore pull in a real Kafka broker too, purely as a side effect of how `lifespan` is wired, for route tests that have nothing to do with Kafka — coupling failure attribution across an unrelated dependency, the same problem later named explicitly for the planned end-to-end tier (see Later). Weighed against what a real-DB route test would uniquely catch beyond the rest of the suite: HTTP status/shape and exception→status-code mapping need no DB at all (a mocked service exercises FastAPI's serialization identically to a real one); Postgres enum round-tripping is already proven by the repository tests above; and "did the route wire the real service call correctly" is addressed by asserting the *exact* mocked call (`mock.assert_awaited_once_with(...)`), the same discipline used for consumer/producer tests throughout. One concrete bonus: mocking the service layer makes previously-untestable-at-this-level exception paths testable — e.g. `InvalidPlateNumber` → 400 can now be verified even though the real validator (`_is_valid_plate_number`) is still a stub that always returns `True`, since the route test only needs the service to *raise* it, not for real business logic to actually produce it.

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
      conftest.py        # postgres_db fixture: disposable Postgres via testcontainers,
                         #   shared by every repository test under truck/ and assignment/
      assignment/        # test_assignment_repository, test_assignment_service,
                         #   test_assignment_producer, test_assignment_consumer,
                         #   test_assignment_kafka_integration
                         #   (+ conftest.py: the testcontainers KafkaContainer fixture —
                         #   split from postgres_db above, unlike Delivery below)
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
                         #   (+ conftest.py: BOTH the testcontainers KafkaContainer
                         #   fixture AND the postgres_db fixture live in this one
                         #   top-level conftest.py — unlike Fleet, which splits them
                         #   across test/conftest.py and test/assignment/conftest.py,
                         #   since Delivery has no assignment/ subdirectory)
    deployment/
api_collection/         # Bruno API collection (YAML)
infra/
  kafka/
    create_topics.sh    # explicit, versioned topic creation — run automatically by the kafka_init service
  postgres/
    init-databases.sh   # idempotent per-service DB/user creation — run automatically by the
                         #   postgres_init service on every `docker compose up` (not a
                         #   first-boot-only /docker-entrypoint-initdb.d/ hook)
  k8s/
    deploy-local.bat    # builds images, deploys to K8s, starts port-forwarding
    shutdown-local.bat  # tears down the K8s deployment
  DEPLOYMENT.md         # local dev setup: Docker Compose vs Kubernetes
docker-compose.yml       # fleet_service, delivery_service, kafka (KRaft), kafka_init,
                         #   redpanda_console, postgres, postgres_init
.env                     # git-ignored — Postgres admin + per-service credentials (see
                         #   Architecture > Postgres); not committed, no .env.example yet
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
- Repository tests for Fleet (`truck_repository`, `assignment_repository`) and Delivery (`delivery_repository`) rewritten against a real, disposable Postgres via `testcontainers[postgresql]` (see Test Conventions for the `postgres_db` fixture pattern and the event-loop gotcha hit along the way)
- Route tests for Fleet (`truck_routes`) and Delivery (`delivery_routes`) rewritten as `unit` tests mocking the service layer — a reversal of the original plan to move them to `integration`, decided once the repository tests above made a real-DB route test redundant (see Test Conventions for the full reasoning)

**In progress / Next up:**
- Add real persistence for Fleet/Delivery Services (currently in-memory only, lost on restart). Prerequisite for the truck position tracking feature below too, since `tracking_service` will need a real repository. Design decisions already made:
  - **Database per service**, matching the existing Kafka-only inter-service boundary — but one shared `postgres` container in `docker-compose.yml` with two logical databases (`fleet_service`, `delivery_service`), each service only holding credentials to its own — not two separate Postgres containers. Mirrors how Kafka is already one shared broker locally.
  - **Drift between the two databases is accepted, not solved, for now.** The system was already eventually consistent before persistence (Kafka-only communication, no shared transaction), so this isn't a new problem — what changes is that a lost message becomes a permanent drift instead of resetting on restart. The real fix for that specific gap is the transactional outbox pattern (write the Kafka event to an `outbox` table in the same DB transaction as the state change, relay it separately) — deliberately deferred; for now this remains the same known gap as "Producer delivery confirmation" above (visibility-only, no guaranteed delivery).
  - Repository function signatures stay unchanged (`save_truck`, `get_truck_by_id`, etc.) — only their internals move from a dict to a real DB, so routes/services/consumers don't change at all. Each repository call opens/closes its own session (no cross-call atomic transactions within a service — a known simplification).

  Planned sequence:
  1. ✅ `docker-compose.yml` `postgres` + `postgres_init` services and `infra/postgres/init-databases.sh` (see Architecture > Postgres for the mount-path and psql `-c` gotchas).
  2. ✅ `sqlalchemy[asyncio]` + `asyncpg` + `alembic` added to each service (the usual uv-workspace install gotcha applied — see Test Conventions). `app/clients/db_client.py` added per service, mirroring `kafka_client.py`'s shape: `start_db()`/`stop_db()`, a `get_session()` context manager, and the shared `Base` both services' ORM models inherit from. Each service ran `alembic init -t async migrations` (see Architecture > Alembic migrations for the `env.py` gotchas).
  3. ✅ SQLAlchemy ORM models (`app/models/orm/truck.py`, `.../delivery.py`), kept separate from the Pydantic domain models — Pydantic stays the API/service-layer boundary. `TruckStatus`/`DeliveryStatus`/`DeliveryDenialReason` are reused directly as `Mapped[SomeEnum]` column types. `Delivery.assigned_truck_id` stays a plain column, never a `relationship()`/`ForeignKey` to `Truck` — Fleet and Delivery are separate Postgres databases, so a cross-database FK isn't possible anyway. `Truck.status` stays stored, not derived (see the `Assignment` history idea under Later for the alternative).
  4. ✅ `truck_repository`/`assignment_repository`/`delivery_repository` rewritten against Postgres — signatures unchanged (now `async def`), one deliberate rename (`delivery_repository.save` → `save_delivery`, matching `save_truck`'s naming), explicit `_to_orm`/`_from_orm` mapping pairs (no `from_attributes` shortcut). `db_client.get_session()` wraps `.begin()`, so every call gets commit-on-success/rollback-on-exception for free.
  5. ✅ First Alembic migration for both services, generated and applied (see Architecture > Alembic migrations for the gotchas). Found and fixed a real bug along the way: `get_truck_by_plate_number` did a primary-key lookup via `session.get()` using `plate_number` instead of `id`, so duplicate-plate validation always silently passed — fixed to `select().where(...)`, with `plate_number` given `unique=True` and a follow-up migration to enforce it in Postgres too.
  6. ✅ Service-layer tests stay `unit` (repository, and Delivery's producer, mocked with `AsyncMock`). Repository tests moved to `integration` via `testcontainers[postgresql]`. Route tests were originally planned to move to `integration` alongside them, but that plan was reversed once the repository tests made a real-DB route test redundant — routes stay `unit`, mocking the service layer instead (see Test Conventions > Route test convention for the full reasoning). CI/CD (running `integration` tests only on push) was raised and explicitly deferred — not decided yet.
  7. A script to seed the database with a variety of test data, for easier manual testing — once there's a real schema to seed.
- Add a volume for Kafka too (currently none, flagged by its own `TODO` in `docker-compose.yml`) — separate from the Postgres persistence work above.
- **✅ Done — Redesign the `kafka` + `integration` tests to mock the service layer**, for both Fleet Service (7 cases) and Delivery Service (5 cases) — see Kafka > Test strategy above for the full breakdown, fixture patterns, and the `auto_offset_reset` gap this surfaced in both services' `kafka_client.py`.
- **Add a dedicated end-to-end test tier**, spanning both services, alongside the existing per-service `unit`/`kafka + integration` tests. Motivating gap: every test in the project today (unit and `kafka + integration` alike) is scoped to one service's own code and its own copy of the Kafka message schemas — and Fleet's and Delivery's copies of `TruckAssignmentRequest`/`TruckAssignmentCompleted` are deliberately independent, not shared (see Kafka above). A schema drift between the two (e.g. one side renaming a field) would pass every existing test undetected, since each side only ever checks its own copy against itself — only a real cross-service test can catch that class of bug. Design constraints already identified:
  - Both services' internal package is literally named `app` (`apps/fleet_service/app`, `apps/delivery_service/app`), so a single Python test process can't import both at once — they'd collide. E2E tests are therefore necessarily true black-box tests against real, running HTTP endpoints (via `docker compose up`, or two separately-launched `uvicorn` processes), never in-process imports the way every existing suite works.
  - Likely doesn't need direct DB access or `testcontainers[postgresql]` at all: the API's own documented contract already exposes the eventually-consistent result through the public surface (`POST /trucks` on Fleet, `POST /deliveries` on Delivery, then poll `GET /deliveries/{id}` until it leaves `REQUESTED`) — asserting through that surface is more faithful "black box" testing than reaching into either service's internal schema/DB directly, and sidesteps the package-name collision above entirely.
  - Consumer-driven contract testing (e.g. Pact) was raised as a lighter-weight alternative/complement specifically for the schema-drift risk, without needing to run both services together — noted as probably more infrastructure than this project needs right now, not pursued for now.
  - Not decided yet: exact test folder location (a new top-level folder outside `apps/`, separate from both services' own `test/`, is the likely shape, since it belongs to neither service alone) or CI wiring.

**Later:**
- Malformed messages (pydantic `ValidationError`) on both `truck-assignment-requested` and `truck-assignment-completed` are currently logged and committed (i.e. dropped) rather than routed anywhere — whether a dead-letter topic is needed is still open (flagged by `TODO`s in both consumers)
- An `Assignment` history table in Fleet Service (`delivery_id`, `truck_id`, timestamp, outcome) — today no assignment record is ever persisted, only the resulting `Truck.status` flip (`assignment_repository.py` doesn't store anything, it just queries `truck_repository` live). A history table would enable auditing, and could let `Truck.status` become derived (computed from open/unresolved assignments) instead of stored — at the cost of a more expensive availability query and needing an explicit signal for when an assignment ends, which nothing produces yet
- Monitoring and logging (e.g., Prometheus/Grafana, ELK stack)
- Organize `docker-compose.yml`'s growing container list (~a dozen services now: `fleet_service`, `delivery_service`, `kafka`, `kafka_init`, `redpanda_console`, `postgres`, `postgres_init`) for readability. Options worth weighing: Compose `profiles` (start subsets, e.g. `--profile kafka` vs. everything), splitting into multiple compose files combined via `-f`, or just better in-file grouping/comments. Leaning toward splitting into multiple files by directory, tentatively something like `apps/`, `init/`, `database/`, `queue/` — open question is whether to group by resource (e.g. `kafka` + `kafka_init` + `redpanda_console` together) or by lifecycle role (all one-shot init jobs together regardless of resource). Not decided yet.
- Add a database UI for manually browsing/querying Postgres content, parallel to Redpanda Console's role for Kafka — candidates raised: pgAdmin (heaviest, full-featured), Adminer (lightweight, generic), pgweb (lightweight, Postgres-only). Would likely connect as `fleetpulse_admin` to browse both `fleet_service` and `delivery_service` from one instance, since it's a human inspection tool rather than a service credential. Not decided yet; likely lands in the `database/` group above once the container reorg above happens.
- Auto-run `alembic upgrade head` on `docker compose up` per service, instead of a manual local command. Likely shaped like `kafka_init`/`postgres_init` — either a one-shot `*_migrate` service per app service, or a migration step in each app container's entrypoint before `uvicorn` starts — and must run after `postgres_init`'s schema grants (see "Postgres 15+ schema-privilege gotcha" above).

## Planned Features

### Truck position tracking
- `gps_simulator` — a new service, a bare `asyncio` worker rather than a FastAPI app (no inbound HTTP traffic, nothing calls it — a real truck's telematics unit wouldn't expose a web API either). Loops over active trucks and produces a position update onto a new `truck-position-updates` topic on an interval (target ~10s–1min), walking along a route obtained from an external routing API.
- Routing: a call to an external routing API to get the path from pickup to dropoff. OSRM's public demo server (`router.project-osrm.org`) is the likely choice for a learning project, since it needs no API key.
- `tracking_service` — a new FastAPI service: consumes `truck-position-updates`, keeps an in-memory `{truck_id: latest_position}` cache (serves live reads without touching Kafka/DB per request), persists to a repository on a throttle rather than on every message (storage only needs a rough idea of where a truck is, not perfect accuracy), and exposes a WebSocket endpoint so clients get live position pushes.
- Open design question, deliberately deferred until both services exist: should `gps_simulator` produce directly onto Kafka, or call an HTTP route on `tracking_service` which produces on its behalf?
- `truck-position-updates` will likely be a compacted topic (`cleanup.policy=compact`, keyed by `truck_id`), since only the latest position matters — unlike the existing two topics, which use default retention.
- Map UI: a frontend visualizing live truck positions on a map, built once the backend above exists. Mainly for a visual/demo payoff rather than FastAPI/Kafka practice, so it's the last piece, not the first.

### Truck maintenance
Truck unavailability for a scheduled repair window (`IN_REPAIR` status with a start/end time). Parked for now.

### Availability-aware delivery scheduling
Allow scheduling a delivery on a truck that is currently unavailable but will become available by the delivery time, instead of only considering trucks available right now. Parked as a later task.
