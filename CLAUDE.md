# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FleetPulse is a learning project for Python microservices. It consists of two FastAPI services that communicate asynchronously via Kafka, deployed locally via Docker Compose or Kubernetes.

## Common Commands

**Install dependencies (from a service directory):**
```bash
uv sync
```
Each service is a standalone uv project (own `pyproject.toml`, `uv.lock`, `.venv`) — there is no root workspace any more. `uv sync` creates the `.venv`, installs production dependencies plus the `dev` and `tooling` groups (via `default-groups`), and downloads Python 3.14 if needed. `uv` itself must be installed machine-wide (standalone installer or `winget install astral-sh.uv`), not inside a venv. Change dependencies with `uv add`/`uv remove` (or edit `pyproject.toml` and re-run `uv sync`); commit `uv.lock` alongside. See Test Conventions > Dependency management.

**Run a service locally:**
```bash
uvicorn apps.fleet_service.app.main:app --reload --port 8001
uvicorn apps.delivery_service.app.main:app --reload --port 8002
```
`gps_simulator` isn't a FastAPI app — no uvicorn, no port. Run it directly instead, from inside `apps/gps_simulator`: `.venv/Scripts/python.exe -m app.main`.

**Run tests for a service** (each service has its own local `.venv`, created by `uv sync`; `uv run pytest test -q` from inside the service directory is equivalent):
```bash
cd apps/fleet_service && .venv/Scripts/python.exe -m pytest test -q
cd apps/delivery_service && .venv/Scripts/python.exe -m pytest test -q
cd apps/gps_simulator && .venv/Scripts/python.exe -m pytest test -q
```

**Run tests by marker** (from inside the service directory, same interpreter as above):
```bash
.venv/Scripts/python.exe -m pytest test -m routes
.venv/Scripts/python.exe -m pytest test -m "unit and not integration"
```
Note `integration` isn't Kafka-specific — repository tests (`test_truck_repository.py`, `test_assignment_repository.py`, `test_delivery_repository.py`, `test_journey_repository.py`) are `integration` too, backed by a real Postgres via `testcontainers[postgresql]` (see Test Conventions). At this point `integration` effectively means "needs Docker" project-wide — route tests moved the other way and are `unit` now (mocked service layer, no DB, no Docker; see Test Conventions for why that plan changed from the original one). To exclude only the slower/flakier `testcontainers`-backed Kafka broker round-trip tests while still running the (Postgres-backed) repository tests, use `-m "not (kafka and integration)"` instead of the broader `-m "not integration"`.

**Run all three apps' tests sequentially, from the repo root:**
```bash
./run-tests.bat                                          # full suite, all three apps
./run-tests.bat -m "not (kafka and integration)"          # skip the Kafka container tests
```
Runs Delivery Service's tests, then Fleet Service's, then `gps_simulator`'s, one after the other, stopping at the first failure; any arguments after the script name are forwarded to all three `pytest` invocations. Since a non-zero exit stops the script, a marker filter that selects nothing in one app (e.g. `-m routes`, which `gps_simulator` has no tests for) makes pytest exit with code 5 ("no tests collected") there and the script reports a failure. PyCharm's `CompoundRunConfigurationType` always launches child configurations simultaneously with no setting to make it sequential, which causes Kafka container contention when both services' `kafka` + `integration` tests run at once (see Test Conventions) — this script is what a "run all tests" PyCharm configuration should point at instead (as a Batch run configuration).

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
Alembic migrations and database seeding run automatically as part of `docker compose up`, via one-shot `*_migration`/`*_seed` services per app (see Architecture > Alembic migrations and Architecture > Database seeding below) — no manual `alembic upgrade head` or seed script invocation needed for a Docker Compose run.

See `infra/DEPLOYMENT.md` for details on both options.

**Check Kafka topics were created (after `docker compose up`):**
```bash
docker compose logs kafka_init
docker compose exec kafka kafka-topics --list --bootstrap-server localhost:9092
```

## Architecture

Two FastAPI microservices plus a bare `asyncio` worker (`gps_simulator`), each owning its own Postgres database (see Postgres below).

### Fleet Service (port 8001)
Manages trucks. Layers: `routes → service → repository → models`.
- `POST /trucks`, `GET /trucks` — public API
- Also runs a Kafka consumer/producer that handles truck assignment requests from Delivery Service (see Kafka below)

### Delivery Service (port 8002)
Manages deliveries. Same layer structure, plus Kafka producer/consumer clients for talking to Fleet Service asynchronously.
- `POST /deliveries`, `GET /deliveries`, `GET /deliveries/{id}`
- On delivery creation, it produces a truck-assignment request onto Kafka and returns immediately with status `REQUESTED`; the eventual `ASSIGNED`/`DENIED` outcome arrives via a Kafka consumer and is only visible on a later `GET /deliveries/{id}`.

### GPS Simulator
A bare `asyncio` worker, not a FastAPI app — no port, no inbound HTTP, nothing calls it. It exists to mock a physical GPS tracker (see Planned Features > Truck position tracking for the full intended design); today it consumes `truck-departure-scheduled` and persists each one as a `Journey` in its own Postgres database, and stops there — no OSRM call, no tick loop, no producer yet.
- Same layered structure as the other two services (`consumers/ -> services/ -> repositories/ -> models/`), but the domain entity is named `Journey`, not `TruckDeparture` — a deliberate move away from naming everything after the Kafka message that creates it. `TruckDepartureScheduled` (the message model, `app/models/truck_departure.py`, alongside its `Coordinates` value type) describes one event; `Journey` (`app/models/journey.py`) is gps_simulator's own entity for that truck's whole tracked movement, expected to grow well past the message's fields — a cached OSRM route, and eventually some progress/status for the tick loop — the same way `Delivery` grew beyond `CreateDeliveryRequest` in Delivery Service. `Journey` imports `Coordinates` from the message-model file, not the reverse, keeping the wire-format type self-contained rather than depending on gps_simulator's internal domain modeling — matching Delivery Service's own precedent of defining `Coordinates` alongside its message model. The consumer (`departure_consumer.py`, `handle_truck_departure_scheduled`) keeps "departure" in its name on purpose, since its job specifically is reacting to that event; only the entity it builds and the layers below it (`journey_service.py`, `journey_repository.py`) use the new naming.
- `journey_repository.save_journey` persists to gps_simulator's own Postgres database (`journeys` table, one row per `delivery_id`), via the same `db_client.py` shape as the other two services. The consumption pipeline (consumer -> service -> repository) was deliberately built and tested against a logging stub first, before adding real Postgres, so its shape got validated against an actual message rather than guessed at. Things specific to this repository:
  - **Idempotent on redelivery:** `save_journey` uses `session.merge`, not `session.add` — `delivery_id` is the primary key, so a redelivered `truck-departure-scheduled` message (see Kafka > Offset commit contract) updates the existing row instead of raising a unique violation, which would otherwise never be committed and be redelivered forever. `merge` is a SELECT followed by an INSERT/UPDATE, not an atomic upsert — acceptable with one consumer on a one-partition topic.
  - **Coordinates are a SQLAlchemy `composite`:** the ORM model (`app/models/orm/journey.py`) maps `pickup_location`/`dropoff_location` to a `CoordinatesORM` dataclass over four `Double` columns (`pickup_lat`, `pickup_lon`, `dropoff_lat`, `dropoff_lon`), so the ORM object keeps the same nested shape as the domain `Journey`.
  - **Mapping lives in the repository, as private functions** (`_journey_to_orm`/`_journey_from_orm`, `_coordinates_to_orm`/`_coordinates_from_orm`), same as Fleet's and Delivery's `_to_orm`/`_from_orm` — chosen over `to_model()`/`from_model()` methods on the ORM class, which would make the persistence model import the domain model; the repository is the one place that has to know both types anyway. The names are type-prefixed here, unlike the other two services' bare `_to_orm`, because this repository maps two types and Python has no overloading — two module-level functions both named `_to_orm` silently rebind, the second replacing the first.
  - The ORM class itself is named `Journey` (imported as `JourneyORM` in the repository), unlike `TruckORM`/`DeliveryORM` in the other services — not reconciled.
  - Reads are `get_journeys()` (all rows, no `ORDER BY` — callers can't rely on ordering) and `get_journey_by_delivery_id()` (returns `Journey | None` via `session.get`, not raising on a missing id); `clear()` deletes every row and exists for the tests' `clear_repository` fixture.
- **Open issue — naive vs aware `departure_time`:** the `journeys.departure_time` column is `DateTime(timezone=True)`, but Delivery Service validates `requested_datetime` against a naive `datetime.today()`, so the `departure_time` it sends is naive too. Observed while writing the repository tests (on a UTC+2 Windows host): a naive value is interpreted in the process's local timezone on the way in, and comes back as an aware UTC datetime — saving naive `18:15` read back as `16:15+00:00`. So the stored instant depends on where the process runs (UTC in the container, the host's timezone on a local run), and a round-tripped `Journey` never compares equal to the naive one that was saved. The repository and service tests sidestep this by using aware datetimes (`datetime.now(timezone.utc)`); no test pins the naive behaviour yet. Matters as soon as the tick loop compares `departure_time` to "now". Still needs a dedicated test, and probably a fix upstream in Delivery Service (see Project Status).
- No FastAPI `lifespan` means no framework-provided signal handling either. `main.py` starts the DB engine, then the consumer — in that order, since a message already waiting on the topic can reach `save_journey` as soon as the consumer starts, and would raise `DB engine is not started` (uncaught, so not committed and not retried until the next restart). Shutdown is the reverse: consumer first, then DB. In between it blocks on a never-set `asyncio.Event` inside a `keep_app_alive()` helper, which registers `SIGTERM`/`SIGINT` handlers that set it — `loop.add_signal_handler` is tried first (it hooks directly into the event loop's own wakeup mechanism, so it reliably interrupts even while the loop is parked on socket I/O, unlike plain `signal.signal` which is only checked between bytecode instructions), falling back to `signal.signal` on `NotImplementedError` — `add_signal_handler` isn't implemented on Windows, which matters here specifically because the local `.venv` workflow (see Test Conventions) means this can be run directly on a Windows host, not just inside the Linux container. This is what uvicorn already does internally for Fleet/Delivery's own graceful shutdown; gps_simulator has to do it by hand since there's no server providing it.
- **Gotcha hit building this:** `docker-compose.yml`'s `gps_simulator` entry initially had no `depends_on` at all, unlike Fleet/Delivery which both wait on `kafka: condition: service_healthy` and `kafka_init: condition: service_completed_successfully`. On a fresh `docker compose up` it started immediately alongside `kafka` instead of after it, tried to bootstrap against a broker that wasn't listening yet, and crashed (`aiokafka.errors.KafkaConnectionError`, `Errno 111` connection refused) before Kafka's `start_period` healthcheck had even passed. Fixed by adding the same `depends_on` block the other two services already carry.
- **Also hit early on:** `pydantic` was added to `requirements.txt` (used for the Docker image) without also being added to `pyproject.toml`'s `dependencies` (used for the local `.venv`) — the two manifests drifted, and the local venv couldn't import the app's own models (`ModuleNotFoundError: No module named 'pydantic'`) until `pyproject.toml` was fixed and `pip install -e .` re-run. Same underlying lesson as the uv-workspace gotcha in Test Conventions: nothing keeps these two files in sync automatically for any service in this project. It happened again adding Postgres: `python-dotenv` (imported by `migrations/env.py` for local runs) is in `requirements.txt` but still not in `pyproject.toml` — it only works locally because it was installed into the venv by hand. Fixed on the local side by the dependency rework (see Project Status > Done): `pyproject.toml` now declares everything, `python-dotenv` included; the `requirements.txt` files still exist only until the Dockerfiles stop using them.
- **`greenlet` gotcha hit adding Postgres:** `alembic revision --autogenerate` failed locally with `ImportError: The SQLAlchemy asyncio module requires that the Python 'greenlet' library is installed`. The local venv had SQLAlchemy 2.1 installed as plain `sqlalchemy`, without the `[asyncio]` extra that `pyproject.toml` declares — and `greenlet` is only pulled in by that extra. Fixed by re-syncing the venv from `pyproject.toml` (`.venv/Scripts/python.exe -m pip install -e .`) rather than installing packages one by one. No longer reachable now that the venv is only ever built by `uv sync` from the lockfile.

### Inter-service communication
Fleet Service and Delivery Service communicate exclusively via Kafka — there is no direct HTTP call between them. See Kafka below for the topics and the message flow.

### Kafka
A single-node broker (`confluentinc/cp-kafka`, KRaft mode — no Zookeeper) runs as the `kafka` service, with a combined `broker,controller` role and three listeners: `CLIENT` (`kafka:9092`, for other containers), `EXTERNAL` (published to the host as `localhost:9094`, so non-containerized local runs like plain `uvicorn` can reach the broker too — Kafka's advertised-listener metadata means one listener can't serve both), and `CONTROLLER` for KRaft's Raft consensus. The `kafka:9092` value is defined once via a YAML anchor (`x-kafka-bootstrap: &kafka-bootstrap kafka:9092` in `docker-compose.yml`) and referenced (`*kafka-bootstrap`) from every service that needs it, instead of repeating the literal four times.

Topics are created explicitly by a one-shot `kafka_init` service, which runs `infra/kafka/create_topics.sh` (a POSIX `sh` script, idempotent via `--if-not-exists`) once `kafka` reports healthy, then exits. The script reads its bootstrap URL from `KAFKA_BOOTSTRAP_SERVERS` (`KAFKA_URL="${KAFKA_BOOTSTRAP_SERVERS:-kafka:9092}"`), which `kafka_init` gets from the anchor above. Both app services `depends_on` both `kafka` (`condition: service_healthy`) and `kafka_init` (`condition: service_completed_successfully`), so they don't start until the broker is up and topics exist.

Topics (1 partition, replication factor 1 — single-broker local setup):
- `truck-assignment-requested` — produced by Delivery Service, consumed by Fleet Service
- `truck-assignment-completed` — produced by Fleet Service, consumed by Delivery Service
- `truck-departure-scheduled` — produced by Delivery Service on a successful assignment, consumed by `gps_simulator` (see Architecture > GPS Simulator)

A `redpanda_console` service (Redpanda Console, image `docker.redpanda.com/redpandadata/console`) is also in `docker-compose.yml`, giving a web UI at `http://localhost:8080` for browsing topics/messages and consumer groups on the local broker. It connects to `kafka:9092` and waits on the same `kafka` (healthy) / `kafka_init` (completed) conditions as the app services.

### Postgres

A shared `postgres` container (`postgres:18.6-bookworm`) provides the database for all three services — one container, three logical databases (`fleet_service`, `delivery_service`, and `gps_simulator`'s, named by `GPS_SIMULATOR_DB_NAME`), each with its own restricted user, mirroring the Kafka pattern above. Data persists in a named volume (`postgres_data`), mounted at `/var/lib/postgresql` rather than `.../data` — Postgres 18+ manages a version-specific data subdirectory itself under a single parent mount (this is what enables `pg_upgrade --link`); mounting straight onto the old `.../data` path throws a startup error on 18+ ("configured to store database data in a format which is compatible with pg_ctlcluster").

Credentials come from a git-ignored `.env` file at the repo root (`POSTGRES_ADMIN_USER/PASSWORD`, shared `POSTGRES_HOST/PORT`, and per-service `FLEET_SERVICE_DB_USER/PASSWORD/NAME` / `DELIVERY_SERVICE_DB_*` / `GPS_SIMULATOR_DB_*` triples), interpolated into `docker-compose.yml`. Each app service's `environment:` block aliases its own triple onto the generic `POSTGRES_HOST/PORT/DB/USER/PASSWORD` names — the shape `db_client.py` and each service's `migrations/env.py` read from `os.environ`, with `POSTGRES_HOST` defaulting to `localhost` (mirroring `kafka_client.py`'s `KAFKA_BOOTSTRAP_SERVERS` default) so local tools work without Docker. `postgres` also publishes `5432:5432` to the host for the same reason as Kafka's `EXTERNAL` listener. The env file must be named exactly `.env` at the repo root — Compose only auto-loads that name. `POSTGRES_USER`/`PASSWORD` on the `postgres` service itself just bootstrap its own admin superuser (`fleetpulse_admin`) on first boot; that's not what the app services connect with at runtime.

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

**Automatic migrations via Docker Compose:** `docker-compose.yml` also defines `fleet_service_migration`/`delivery_service_migration`/`gps_simulator_migration`, one-shot services following the same pattern as `kafka_init`/`postgres_init` — built from the same image as their app service, running `alembic upgrade head` as their `command` instead of `uvicorn`, `depends_on: postgres_init` (completed), and exiting once done. Each app service in turn `depends_on` its own migration service (completed), so `docker compose up` always applies pending migrations before the app starts — a manual `alembic upgrade head` is still needed only for local `uvicorn` runs outside Docker. Building this surfaced a Dockerfile gap: both Dockerfiles originally only `COPY`d the `app/` directory, so the migration service failed (missing `alembic.ini`/`migrations/` in the image) until `COPY migrations` and `COPY alembic.ini` were added alongside it.

### Database seeding

Each service has its own `scripts/seed_data.py` (`apps/fleet_service/scripts/`, `apps/delivery_service/scripts/`), a standalone script outside `app/` that clears its service's tables (`truck_repository.clear()` / `delivery_repository.clear()`) and reseeds a fixed, varied dataset: Fleet seeds trucks across all three `TruckStatus` values; Delivery seeds deliveries across all four `DeliveryStatus` values, including denial reasons/descriptions for `DENIED` deliveries. Run locally the same way as tests/migrations — the service's own interpreter, e.g. `.venv/Scripts/python.exe -m scripts.seed_data` from inside the service directory.

`docker-compose.yml` runs both automatically via `fleet_service_seed`/`delivery_service_seed`, one-shot services shaped like the migration services above (same image, `command: python -m scripts.seed_data`, `depends_on` their own service's migration completing). Each app service in turn `depends_on` its own seed service (completed).

`gps_simulator` has the same wiring (`gps_simulator_seed`, `apps/gps_simulator/scripts/seed_data.py`), but the script is an empty placeholder for now — it exists so the seed service completes and `gps_simulator` can start; it seeds nothing and clears nothing, even though `journey_repository.clear()` now exists. Whether it ever gets real content, or is replaced by a single scenario-grouped seed script, is still open (see Project Status > Later).

**Design decision: reseeds on every `docker compose up`, deliberately.** Because both scripts `clear()` before reseeding, any data created manually through the API (`POST /trucks`, `POST /deliveries`) is wiped the next time the stack comes up — intentional, not a gap. Rationale: it forces a reproducible testing environment on every run, and pushes any data needed repeatedly for manual testing into the seed script itself (keeping it accurate and current) rather than accumulating ad-hoc, undocumented state through the API that only ever exists in one person's local database.

The two scripts are fully independent — no `depends_on` ordering between `fleet_service_seed` and `delivery_service_seed`, and neither script reads the other service's database. They do share a hardcoded pool of 50 truck IDs (`IN_USE_TRUCK_IDS` in Fleet's script, `TRUCK_IDS` in Delivery's — same literal list, `Should match fleet_service seed_data.py repartition` comment in both) so that Delivery's seeded `assigned_truck_id` values line up with trucks Fleet's script actually seeds — a data-narrative convenience, not an enforced or checked constraint.

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

**Producer delivery confirmation:** `aiokafka`'s `AIOKafkaProducer.send()` only confirms the message was queued locally (topic metadata resolved, placed in the batch accumulator) — it returns an `asyncio.Future` that resolves separately once the broker actually acknowledges the write (`send_and_wait` is `future = await send(...); return await future`, which adds a full broker round-trip to the caller). Every producer module in both services stays fire-and-forget on that round-trip — they don't await the future, to avoid adding broker latency to the request path — but do capture it and attach `future.add_done_callback(functools.partial(log_send_failure, topic, delivery_id))`. `log_send_failure` reads `future.exception()` (not `.result()`, which would just re-raise inside the callback instead of being observable) and, if not `None`, logs it via `logger.error(..., exc_info=exc)` (not `logger.exception`, since that reads from `sys.exc_info()`, only populated inside an active `except` block). This is visibility only — a genuine broker-level failure (timeout, leader unavailable, etc.) is still lost, just no longer silent; no retry or dead-letter mechanism exists yet.

The two services currently diverge on where this function lives. Delivery Service centralized it as `kafka_client.log_send_failure`, a shared function on the client module, once a second producer (`departure_producer.py`, see Planned Features > Truck position tracking) needed the identical logic — its own `assignment_producer.py` was updated to call `kafka_client.log_send_failure` instead of keeping a private copy. Fleet Service still has only one producer module, so its `assignment_producer.py` keeps its own private `_log_send_failure`, never centralized. Not yet reconciled — Fleet would hit the same duplication pressure the moment it grows a second producer.

**Test strategy:**
- `kafka` pytest marker, combined with the existing `unit`/`integration` markers.
- `kafka` + `unit`: mocked `aiokafka` producer/consumer, testing call-shape (correct topic/payload on produce) and message-handling logic (correct status transition on consume) in both services. Runs every time, no external dependency.
- `kafka` + `integration`: round-trip smoke tests against a disposable broker spun up via `testcontainers[kafka]` — not the docker-compose Kafka instance, to keep tests isolated. Fleet Service: `test/assignment/kafka_integration/test_assignment_kafka_integration.py` + its own `conftest.py`. Delivery Service: `test/kafka_integration/test_assignment_kafka_integration.py` + its own `conftest.py`. Each fixture is a module-scoped `KafkaContainer` (via `testcontainers.community.kafka`) started `.with_kraft()` (matching how the real docker-compose broker runs) with both topics created explicitly through `aiokafka`'s `AIOKafkaAdminClient`, mirroring `infra/kafka/create_topics.sh`. Tests point `kafka_client.KAFKA_BOOTSTRAP_SERVERS` at the container via `monkeypatch.setattr` (the module reads the env var once at import time, so `monkeypatch.setenv` wouldn't take effect), start the app's real producer/consumer, and assert the expected outcome — either a message arriving on a throwaway consumer, or a repository record updating — polled with `asyncio.wait_for(..., timeout=15)` rather than a fixed sleep. These tests are `async def` using `pytest-asyncio` (`asyncio_mode = "strict"`), unlike the `kafka` + `unit` tests, since round-tripping through a real broker means running a background consumer task concurrently with producing and awaiting the result.
- Running both services' `kafka` + `integration` tests at the same time can be flaky: two Kafka JVM brokers cold-booting concurrently on the same Docker Desktop instance occasionally contend for resources. Run them sequentially (`run-tests.bat`, the documented default) for reliability; if a concurrent run does fail this way, retrying alone usually passes.
- Rationale: verifying Kafka itself works isn't this project's responsibility (the broker health check plus `kafka_init`'s explicit topic creation already cover that); verifying *our* producer/consumer contract with Kafka is.
- **Both services' `kafka` + `integration` suites were redesigned to mock the service layer**, instead of seeding a real truck/delivery through the real repository — that coverage now belongs to the repository tests (see Test Conventions). Each suite mocks its own service call (`assignment_service.assign_truck_to_delivery` in Fleet, `delivery_service.update_delivery_with_truck_assignment` in Delivery) and tests purely the Kafka contract: real broker (via `testcontainers`), real serialization, real consumer/producer wiring, no DB.
  - **Fleet** (`test/assignment/kafka_integration/test_assignment_kafka_integration.py`, `TestAssignmentKafkaIntegration`, 7 cases): successful assignment produces the right completed message on the real broker; `UnknownDelivery`/`InvalidCargoWeight`/`NoTruckAvailable` each map to the right `DENIED` reason (`INVALID_REQUEST` / `NO_AVAILABLE_TRUCK`); an uncaught `RuntimeError` gets the message redelivered after a forced consumer restart; a *successful* handling does not get redelivered after that same forced restart; a malformed request message is dropped without the service ever being called.
  - **Delivery** (`test/kafka_integration/test_assignment_kafka_integration.py`, `TestDeliveryKafkaIntegration`, 5 cases): same shape, minus the two-reason split — `handle_truck_assignment_completed` only ever catches one exception, `NotFoundException`, since a *completed* message was already validated on Fleet's side. Delivery's consumer also produces nothing in response, so every test here polls the mocked service call directly instead of an output topic.
  - **gps_simulator** (`test/kafka_integration/test_departure_kafka_integration.py`, `TestDepartureKafkaIntegration`, 4 cases, mocking `journey_service.create_journey`): same shape as Delivery's, minus the caught-exception case — `handle_truck_departure_scheduled` catches nothing besides `ValidationError`. A valid message reaches the service as the parsed `TruckDepartureScheduled`; an uncaught `RuntimeError` gets redelivered after a forced restart; a successful handling does not; a malformed message is dropped. Differences from the other two suites: the injected message is a hand-written dict in wire format (`departure_time` as an ISO 8601 string, as Delivery's `model_dump(mode="json")` sends it) rather than a dump of gps_simulator's own model, so the test checks the cross-service shape rather than the model against itself; its conftest creates only the `truck-departure-scheduled` topic, has no raw `kafka_consumer` fixture, and its autouse fixture (`running_departure_consumer`) starts only the consumer, since gps_simulator's `kafka_client` has no producer; and the redelivery test sleeps 0.5s after the second delivery so the offset commit lands before teardown — otherwise the consumer can be stopped between the handler returning and the commit, leaking the message into the next test (Fleet's and Delivery's redelivery tests have the same theoretical race and no such wait).
  - Fixture pattern in both: an `autouse` pair — `mock_kafka_bootstrap_servers` (points `kafka_client.KAFKA_BOOTSTRAP_SERVERS` at the test container) and `running_assignment_consumer_and_producer` (starts/stops the app's real producer + consumer around each test) — plus explicit `kafka_consumer`/`kafka_producer` fixtures for injecting/observing raw messages where a test still needs to. Both services keep these in a dedicated `kafka_integration/` subdirectory's own `conftest.py` (`test/assignment/kafka_integration/` for Fleet, `test/kafka_integration/` for Delivery) — see the directory-scoping gotcha immediately below for why that subdirectory exists at all.
  - **Directory-scoping gotcha (found via a `kafka` + `unit` test unexpectedly spinning up a real broker):** pytest conftest fixtures — `autouse` ones included — apply per-*directory*, not per-marker. Both services originally put the real-broker fixtures (`kafka_bootstrap_servers`, `mock_kafka_bootstrap_servers`, `running_assignment_consumer_and_producer`) directly alongside their `kafka` + `unit` producer/consumer test files: Fleet in `test/assignment/conftest.py`, shared with `test_assignment_producer.py`/`test_assignment_consumer.py`; Delivery in one flat top-level `test/conftest.py`, shared with its entire `test/` tree. Because `autouse=True` fixtures fire for every test collected in their directory regardless of that test's own markers, the fully-mocked `kafka` + `unit` tests — which are supposed to have zero external dependencies per the Test strategy above — were transitively pulled into starting a real `testcontainers` Kafka broker anyway, surfacing as an intermittent `RuntimeError: Container exited ... before emitting logs containing 'Kafka Server started'` even when running `pytest -m unit` alone. Fix: move `test_assignment_kafka_integration.py` and the real-broker fixtures into their own `kafka_integration/` subdirectory in both services (nested under `assignment/` for Fleet, since Fleet already splits `truck/` vs `assignment/` by domain; directly under `test/` for Delivery, which has no equivalent domain split to nest under), leaving the `kafka` + `unit` files in a directory with no such autouse fixtures. Named `kafka_integration/` rather than a bare `kafka/`, since the `kafka` marker alone is ambiguous — the mocked producer/consumer tests are `kafka`-marked too — while `kafka_integration` mirrors the `kafka + integration` marker combination that actually requires the real broker.
  - Forcing redelivery requires an actual restart (`kafka_client.stop_consuming()` + `start_consuming()`) — a live consumer session never re-fetches a message it already yielded, commit or not (see Offset commit contract above). Both services hit the same missing-`auto_offset_reset` gap independently while building these tests: without `auto_offset_reset="earliest"`, a restarted consumer with no prior committed offset for the group falls back to `aiokafka`'s own `"latest"` default and skips straight past the very message it should be redelivering. Fleet's `kafka_client.py` was fixed first; Delivery's had the identical gap, never carried over, and only surfaced once Delivery got its own forced-restart test.
  - General test-design takeaway: poll a concrete condition for a *positive* outcome (a mock's `await_count`, a message arriving) rather than sleeping a fixed duration; a fixed sleep is the right tool only for proving a *negative* ("nothing else happened"), since there's no condition to poll toward.

### Data models
- **Truck:** `id`, `plate_number`, `capacity_kg`, `status` (`AVAILABLE` / `IN_USE` / `IN_REPAIR`)
- **Delivery:** `id`, `client_id`, `pickup_location`, `dropoff_location`, `cargo_weight_kg`, `requested_datetime`, `status` (`REQUESTED` / `ASSIGNED` / `DENIED` / `COMPLETED`), `assigned_truck_id`, `denial_reason` (Delivery Service's own `DeliveryDenialReason` enum — currently mirrors `TruckAssignmentFailureReason`'s values but is a deliberately separate type, expected to grow values beyond Fleet Service's technical reasons as the product develops), `denial_description` (free-text detail, set only when `status` is `DENIED`)

## Test Conventions

pytest markers (defined identically in each service's own `pyproject.toml` under `[tool.pytest.ini_options]` — see "Running tests" below for why each service needs its own copy; `gps_simulator`'s copy omits `routes`, since it has no FastAPI routes to test):
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

**Repository test convention (Postgres-backed, done):** the old pattern — an `autouse` fixture calling a synchronous in-memory `clear()` between tests — no longer applies now that repositories are Postgres-backed. Repository tests (`test_truck_repository.py`, `test_assignment_repository.py`, `test_delivery_repository.py`, and gps_simulator's `test_journey_repository.py`) are `repository` + `integration`, backed by a real, disposable Postgres via `testcontainers[postgresql]` (specifically `testcontainers.community.postgres.PostgresContainer` — the base `testcontainers` package already includes it, no extra dependency needed, since Postgres readiness is checked via `psql` inside the container rather than a Python driver). The pattern, defined once per service in a module-scoped `postgres_db` fixture in `test/conftest.py`:
- Start the container with `driver="asyncpg"`, build a `sqlalchemy.engine.URL` from its connection details, and monkeypatch `db_client._build_database_url` directly to return it — not environment variables — since `db_client.py` only reads `os.environ` inside that one function.
- Create the schema with `Base.metadata.create_all` via a throwaway engine rather than running real Alembic migrations — deliberately simpler and faster for tests, at the cost of never exercising the migration files themselves through this path.
- Call the real `db_client.start_db()` so every repository call under test goes through the actual `get_session()`/`async_sessionmaker` code path.
- A separate, function-scoped `clear_repository` fixture (depending on `postgres_db` to guarantee ordering) awaits the repository's own `clear()` before every test, so the container/engine/event loop are shared for the whole module but table state isn't.

**Event-loop gotcha hit building this:** `asyncpg` connections are bound to the event loop they were created on. An early version ran the fixture's setup through its own throwaway `asyncio.run(...)` call, separate from whatever loop `pytest-asyncio` hands each test — the second test then failed deep inside `asyncpg` with a cryptic Windows `ProactorEventLoop` `AttributeError: 'NoneType' object has no attribute 'send'`, since its connection was still bound to the first test's already-closed loop. Fix: make `postgres_db` a real `pytest_asyncio.fixture` and pin everything to one shared loop — the fixture, the `clear_repository` fixture, and the test class all declare `loop_scope="module"` (`@pytest_asyncio.fixture(scope="module", loop_scope="module")`, `@pytest_asyncio.fixture(autouse=True, loop_scope="module")`, `@pytest.mark.asyncio(loop_scope="module")`).

**Route test convention (done, reversed from an earlier plan):** routes stay `routes` + `unit`, mocking the service layer (`truck_service`/`delivery_service`) entirely — not `integration` backed by testcontainers as originally planned (see Project Status history). No `postgres_db` fixture, no `db_client`, no real Kafka; tests are plain sync functions again since `TestClient` handles the async route internally. Reasoning: `TestClient(app)` used without `with` (the pattern every route test file uses) never triggers the app's `lifespan` — confirmed by running a route test against a stale, unmocked repository call and seeing `RuntimeError: DB engine is not started` — and both services' `lifespan` starts a real Kafka consumer *and* the real DB together. Opting into `with TestClient(app) as client:` to get a "fully real" app would therefore pull in a real Kafka broker too, purely as a side effect of how `lifespan` is wired, for route tests that have nothing to do with Kafka — coupling failure attribution across an unrelated dependency, the same problem later named explicitly for the planned end-to-end tier (see Later). Weighed against what a real-DB route test would uniquely catch beyond the rest of the suite: HTTP status/shape and exception→status-code mapping need no DB at all (a mocked service exercises FastAPI's serialization identically to a real one); Postgres enum round-tripping is already proven by the repository tests above; and "did the route wire the real service call correctly" is addressed by asserting the *exact* mocked call (`mock.assert_awaited_once_with(...)`), the same discipline used for consumer/producer tests throughout. One concrete bonus: mocking the service layer makes previously-untestable-at-this-level exception paths testable — e.g. `InvalidPlateNumber` → 400 can now be verified even though the real validator (`_is_valid_plate_number`) is still a stub that always returns `True`, since the route test only needs the service to *raise* it, not for real business logic to actually produce it.

**Running tests:** each service has its own local `.venv` (e.g. `apps/delivery_service/.venv`) built by `uv sync` from that service's own `pyproject.toml` + `uv.lock`. Run tests with the service's own interpreter from inside the service directory, e.g. `cd apps/delivery_service && .venv/Scripts/python.exe -m pytest test -q` (or `uv run pytest test -q` — the old warning against `uv run` only applied while a root workspace lock existed). None of the services is an installed package (no `[build-system]`), so `app` is importable only because the service directory is on `sys.path`: `python -m` adds it, and `pythonpath = ["."]` in each `[tool.pytest.ini_options]` covers bare `pytest`/`uv run pytest`. Doing it that way picks up the service's own `pyproject.toml` `[tool.pytest.ini_options]` as the config — pytest resolves config per-directory, walking up from wherever it's invoked, and stops at the first `pytest.ini`/`pyproject.toml` it finds. Markers live only in each service's own `pyproject.toml`, kept in sync by hand, since the two services intentionally keep independent venvs/configs rather than sharing one workspace-wide test environment.

**Dependency management:** each service's `pyproject.toml` splits its dependencies three ways — production in `[project].dependencies`, test tooling in the `dev` dependency group, and migration/seeding tooling (`alembic`, `python-dotenv`, plus `tqdm` in Fleet and Delivery) in a `tooling` group. `[tool.uv] default-groups = ["dev", "tooling"]` makes a plain `uv sync` install all three locally; without it uv installs only `dev`, and `alembic` goes missing from the venv. Add a dependency with `uv add <package>` (production), `uv add --dev <package>` or `uv add --group tooling <package>` from inside the service directory — it updates that service's own `pyproject.toml`, `uv.lock` and `.venv` together. `uv.lock` is never edited by hand and never regenerated wholesale: it re-locks itself when `pyproject.toml` changes, and existing versions only move on an explicit `uv lock --upgrade` (or `--upgrade-package <name>`). The earlier gotcha here — `uv add`/`uv sync` resolving against a shared root environment — disappeared with the root `[tool.uv.workspace]`. Two `httpx` flavours coexist on purpose: Starlette's `TestClient` now wants `httpx2` (it emits a `StarletteDeprecationWarning` with plain `httpx`), so `httpx2` sits in `dev` for Fleet and Delivery, while Delivery also keeps `httpx` in production because `osrm_client.py` imports it and `respx` mocks it.

## Workspace Layout

```
                         # no root pyproject.toml/uv.lock — the uv workspace was dropped; each
                         #   app below is a standalone uv project with its own pyproject.toml,
                         #   uv.lock and .venv (see Test Conventions > Dependency management)
run-tests.bat            # runs all three apps' tests sequentially (see Common Commands) —
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
    scripts/            # seed_data.py — clears & reseeds a varied truck dataset,
                         #   run automatically by fleet_service_seed (see Architecture >
                         #   Database seeding)
    test/
      conftest.py        # postgres_db fixture: disposable Postgres via testcontainers,
                         #   shared by every repository test under truck/ and assignment/
      assignment/        # test_assignment_repository, test_assignment_service,
                         #   test_assignment_producer, test_assignment_consumer
                         #   (kafka + unit, fully mocked — no Kafka-specific conftest
                         #   fixtures live at this level; see kafka_integration/ below)
        kafka_integration/  # test_assignment_kafka_integration.py + its own conftest.py
                         #   (the testcontainers KafkaContainer fixture, autouse) —
                         #   split into its own subdirectory rather than living directly
                         #   in assignment/, because pytest conftest autouse fixtures
                         #   apply per-directory regardless of marker: when the
                         #   real-broker fixtures lived in assignment/conftest.py, the
                         #   kafka + unit tests sharing that directory inherited them
                         #   too and started spinning up a real Kafka container despite
                         #   being fully mocked (see Kafka > Test strategy)
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
                         #   deliberately not shared with Fleet Service's models),
                         #   truck_departure (TruckDepartureScheduled + nested
                         #   Coordinates — the truck-departure-scheduled message shape,
                         #   see Planned Features > Truck position tracking)
      clients/          # kafka_client (aiokafka, consumer + producer; also holds the
                         #   shared log_send_failure used by both producers below) —
                         #   this service talks to Fleet Service only via Kafka, no
                         #   HTTP client; osrm_client (httpx, async) — city-name
                         #   coordinate lookup + OSRM route-duration calls, see Planned
                         #   Features > Truck position tracking
      consumers/        # assignment_consumer — handles truck-assignment-completed,
                         #   updates delivery status via delivery_service
      producers/        # assignment_producer — produces TruckAssignmentRequest onto
                         #   truck-assignment-requested; departure_producer — produces
                         #   TruckDepartureScheduled onto truck-departure-scheduled,
                         #   kept separate from assignment_producer.py (different topic,
                         #   different concern)
    scripts/            # seed_data.py — clears & reseeds a varied delivery dataset,
                         #   run automatically by delivery_service_seed (see Architecture >
                         #   Database seeding)
    test/                # test_delivery_repository, test_delivery_routes,
                         #   test_delivery_service, test_assignment_producer,
                         #   test_assignment_consumer, test_departure_producer,
                         #   test_osrm_client (kafka + unit, fully mocked)
                         #   conftest.py: postgres_db fixture only — no Kafka-specific
                         #   fixtures live at this level (see kafka_integration/ below
                         #   and Kafka > Test strategy for why)
      kafka_integration/  # test_assignment_kafka_integration.py + its own conftest.py
                         #   (the testcontainers KafkaContainer fixture, autouse) — a
                         #   dedicated subdirectory, not Delivery's original flat layout
                         #   where these fixtures lived in one top-level test/conftest.py:
                         #   being autouse there meant they applied to every test in the
                         #   whole test/ tree, so even test_assignment_consumer.py's
                         #   fully-mocked kafka + unit tests were spinning up a real
                         #   broker (the same bug Fleet hit — see Kafka > Test strategy)
    deployment/
  gps_simulator/
    app/
      clients/          # kafka_client (aiokafka) — consumer only for now; no producer
                         #   until the truck-position-updates topic exists (see Planned
                         #   Features > Truck position tracking); db_client (SQLAlchemy
                         #   async engine/session, same shape as the other two services)
      consumers/        # departure_consumer — handles truck-departure-scheduled, builds
                         #   a Journey and hands it to journey_service
      models/            # truck_departure (TruckDepartureScheduled + Coordinates — the
                         #   message model, gps_simulator's own independent copy of the
                         #   Kafka contract), journey (Journey — the domain model; see
                         #   Architecture > GPS Simulator for why it's named apart from
                         #   the message it's built from), orm/journey (the ORM model
                         #   + CoordinatesORM composite, journeys table)
      services/          # journey_service
      repositories/      # journey_repository — save_journey upserts via session.merge;
                         #   get_journeys, get_journey_by_delivery_id, clear (see
                         #   Architecture > GPS Simulator)
      main.py            # bare asyncio worker entrypoint — starts the DB, then the
                         #   consumer, then blocks on a shutdown Event set by a
                         #   SIGTERM/SIGINT handler (see Architecture > GPS Simulator)
    migrations/          # Alembic — env.py + versions/ (first migration: create
                         #   journeys table), run automatically by gps_simulator_migration
    scripts/             # seed_data.py — empty placeholder so gps_simulator_seed
                         #   completes (see Architecture > Database seeding)
    test/                # test_departure_consumer (kafka + unit, mocks
                         #   journey_service.create_journey), test_journey_service
                         #   (service + unit, mocks journey_repository.save_journey),
                         #   test_journey_repository (repository + integration)
                         #   conftest.py: postgres_db fixture only, same pattern as the
                         #   other two services
      kafka_integration/  # test_departure_kafka_integration.py + its own conftest.py
                         #   (the testcontainers KafkaContainer fixture, autouse) —
                         #   same subdirectory split as the other two services (see
                         #   Kafka > Test strategy)
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
docker-compose.yml       # fleet_service, delivery_service, gps_simulator, kafka (KRaft),
                         #   kafka_init, redpanda_console, postgres, postgres_init,
                         #   *_migration + *_seed one-shot services per app (gps_simulator
                         #   included; its seed script is an empty placeholder)
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
- Real persistence via Postgres added to both services — SQLAlchemy ORM models, `truck_repository`/`assignment_repository`/`delivery_repository` rewritten against `asyncpg` (signatures unchanged), first Alembic migrations generated and applied (see Architecture > Postgres and Architecture > Alembic migrations)
- The `kafka` + `integration` tests redesigned to mock the service layer instead of seeding through the real repository, for both Fleet Service (7 cases) and Delivery Service (5 cases) — see Kafka > Test strategy for the full breakdown, fixture patterns, and the `auto_offset_reset` gap this surfaced in both services' `kafka_client.py`
- Repository tests for Fleet (`truck_repository`, `assignment_repository`) and Delivery (`delivery_repository`) rewritten against a real, disposable Postgres via `testcontainers[postgresql]` (see Test Conventions for the `postgres_db` fixture pattern and the event-loop gotcha hit along the way)
- Route tests for Fleet (`truck_routes`) and Delivery (`delivery_routes`) rewritten as `unit` tests mocking the service layer — a reversal of the original plan to move them to `integration`, decided once the repository tests above made a real-DB route test redundant (see Test Conventions for the full reasoning)
- Alembic migrations and database seeding now run automatically on `docker compose up`, via one-shot `*_migration`/`*_seed` services per app (see Architecture > Alembic migrations and Architecture > Database seeding)
- `Delivery.requested_date` renamed to `requested_datetime` (type changed `date` → `datetime`) — step 1 of the truck-position-tracking plan (see Planned Features below), needed since `departure_time` computation in a later step requires a real moment, not just a date
- **`gps_simulator` scaffolded, and its consumption pipeline built through to real Postgres persistence** (step 4 of Truck position tracking below — partially done; the OSRM route caching and tick loop are still pending): app initialized (own `pyproject.toml`/`.venv`, `requirements.txt`, `Dockerfile`), wired into `docker-compose.yml`; consumes `truck-departure-scheduled` end-to-end through `departure_consumer -> journey_service -> journey_repository`, which upserts the `Journey` into gps_simulator's own database (`db_client.py`, ORM model, first Alembic migration creating `journeys`, `postgres_init`/`gps_simulator_migration`/`gps_simulator_seed` wiring in Compose — see Architecture > GPS Simulator); `kafka` + `unit` tests added for the consumer (`test_departure_consumer.py`), with `pytest`/`pytest-asyncio` wired into its own `pyproject.toml` the same way as the other two services. The domain entity is named `Journey`, not `TruckDeparture` — deliberately moved away from naming everything after the Kafka message that creates it (see Architecture > GPS Simulator for the full rationale). `main.py`, having no FastAPI/uvicorn server loop to keep the process alive or handle shutdown signals, does both by hand — see the same section for how.
- **`gps_simulator` test coverage brought in line with the other two services:** `journey_repository` gained `get_journeys`, `get_journey_by_delivery_id` and `clear`; repository tests (`test_journey_repository.py`, 3 cases — list, get by id incl. missing, and save-twice-updates, the reason `save_journey` uses `merge`) run against a disposable Postgres via a `postgres_db` fixture in `test/conftest.py`; a service test (`test_journey_service.py`) mocks the repository; and a `kafka` + `integration` suite (4 cases) lives in `test/kafka_integration/` (see Kafka > Test strategy). `testcontainers[kafka]` was added to its `pyproject.toml` dev dependency group. Writing the repository tests also confirmed the naive-`departure_time` behaviour (see Architecture > GPS Simulator > Open issue).
- Both services' `kafka` + `integration` tests moved into a dedicated `kafka_integration/` subdirectory (`test/assignment/kafka_integration/` for Fleet, `test/kafka_integration/` for Delivery), fixing a directory-scoping bug where the real-broker `autouse` fixtures were bleeding into the co-located `kafka` + `unit` tests and making them spin up a real Kafka container despite being fully mocked (see Kafka > Test strategy for the full gotcha)
- **Truck position tracking, steps 1–3 done** (see Planned Features > Truck position tracking for the full flow): `app/clients/osrm_client.py` built and tested (`get_city_coordinates`, `get_route_duration`, 5 tests in `test_osrm_client.py`, mocking OSRM's HTTP response via `respx`); `producers/departure_producer.py` built via TDD and tested (mirrors `assignment_producer.py`'s send-and-attach-callback shape); wired into `delivery_service.update_delivery_with_truck_assignment` via a new private `_call_truck_departure_scheduled` helper, called only when `assignment.assigned` is `True`, **after** `save_delivery` — matching `create_delivery`'s existing save-then-produce order, to avoid a window where a departure message could go out but the delivery's `ASSIGNED` status never got persisted. A new `UnassignedTruckOnCompletedAssignment` exception (`app/exceptions.py`) guards against a completed assignment arriving with `assigned=True` but no `truck_id` (boundary validation on Fleet's message, not an internal invariant); `handle_truck_assignment_completed` catches it alongside `NotFoundException` and `UnknownCity` (all three deterministic/permanent — resolve rather than retry) but deliberately **not** `OSRMRequestFailed`, which stays uncaught so a transient OSRM failure still gets redelivered per the existing offset-commit contract, rather than silently dropped. `truck-departure-scheduled` added to `infra/kafka/create_topics.sh`'s auto-created topic list. Along the way, Delivery Service centralized its producer failure-logging callback into `kafka_client.log_send_failure`, shared by both `assignment_producer.py` and `departure_producer.py` instead of each keeping its own private copy (see Kafka > Producer delivery confirmation) — Fleet Service hasn't needed this yet, since it still only has one producer module.
- **Dependency rework, phase 1 (dependencies) done** (see In progress below for the remaining phases): the root uv workspace is gone (root `pyproject.toml` and `uv.lock` deleted), and each of the three services is a standalone uv project whose `.venv` is built by `uv sync` from its own `pyproject.toml` + `uv.lock`. Dependencies are split into production / `dev` / `tooling` (see Test Conventions > Dependency management); `fastapi[standard]` became plain `fastapi` + `uvicorn[standard]` (keeping uvicorn's extra for `uvloop`/`httptools` and for `websockets`, which `tracking_service` will need); the hatchling `[build-system]` block was removed from all three, since no service is ever installed as a package — they are only run from their own directory; and `requires-python` is `>=3.14` everywhere, matching the `python:3.14-slim` images. Verified per service with the full test suite (Docker-backed tests included), a local `alembic upgrade head`, and a seed run for Fleet and Delivery. The Dockerfiles and `requirements.txt` files are untouched so far. Side effect worth knowing: PyCharm derives its modules from `pyproject.toml` files, so deleting the root one removed the repo root from the Project view — fixed locally with a hand-written `.idea/fleetPulse.iml` (no `external.system.id`) registered in `.idea/modules.xml`; `.idea/` is git-ignored, so a fresh clone needs the same fix or the "Project Files" view.

**In progress / Next up:**
- **Truck position tracking — steps 1–3 done (see Done above); step 4 (`gps_simulator`) in progress.** The consumption pipeline (consumer → service → repository) persists to real Postgres and is now tested at every layer (see Done above). Next, in order: (1) **a dedicated timezone test** — pin what happens to a naive `departure_time` stored in the `timestamptz` column (behaviour already observed, not yet asserted), and decide whether Delivery Service should send aware datetimes (see Architecture > GPS Simulator > Open issue); then the hourly departure-check loop and OSRM route-caching/tick simulation described below. Full flow (see Planned Features > Truck position tracking below for the detailed writeup). Remaining divergence still in place: `POST /deliveries` keeps producing `TruckAssignmentRequested` immediately, and Fleet Service keeps assigning purely on current availability (no forward-looking scheduling yet — a deliberate, temporary simplification; see that section for what's deferred).

  `gps_simulator` — a bare `asyncio` worker (no FastAPI, nothing calls it) — see Architecture > GPS Simulator for what's built so far. It already persists each departure as a `Journey` in its own Postgres database; still to come, it will separately call OSRM itself to get the actual route coordinates for simulation — two independent OSRM calls for two genuinely different responsibilities, not a redundant duplicate (see Planned Features for why). That second call needs `overview=full&geometries=geojson&annotations=true`, not just `overview=full` — OSRM's route geometry alone gives coordinates with no timing information, and naively treating elapsed-time-as-percentage-of-points-in-the-list is wrong on two counts: geometry points aren't evenly spaced in distance, and even distance-based interpolation would assume constant speed for the whole route, which breaks the moment a route mixes highway and city stretches. `annotations=true` adds a `duration` array parallel to the coordinate list (time per individual segment), letting the tick loop find which segment the elapsed time falls into and interpolate position within it using that segment's own distance/duration. Its periodic tick loop only acts on deliveries whose `departure_time` has already passed; deliveries scheduled further out just sit in its DB until then, so no separate scheduler/poller component is needed anywhere in this flow.
- **Dependency, image and build rework — phase 1 (dependencies) done, see Done above; phase 2 (Dockerfiles) is the next step, ahead of the truck-position-tracking work below.** Motivation: `requirements.txt` (used by the Dockerfiles) and `pyproject.toml` (used by the local `.venv`) have drifted every time a dependency was added to only one of them (`pydantic`, then `python-dotenv`, both in `gps_simulator` — see Architecture > GPS Simulator). Hosting/deploying the project from CI was considered and explicitly dropped: this is a personal project that stays local, and being installable on a new machine in one command matters far more than being hosted somewhere.

  **Requirements:**
  1. **One dependency declaration per service, efficient across every environment** (local development with test running, Docker Compose builds, CI): drop the three `requirements.txt` files and keep only `pyproject.toml`, with the Dockerfiles updated to install from it.
  2. **Dependencies split by purpose:** production dependencies in `[project].dependencies` (`fastapi`, `uvicorn`, `httpx`, `aiokafka`, `sqlalchemy[asyncio]`, `asyncpg`, ...), test tooling in the `dev` dependency group (`pytest`, `pytest-asyncio`, `respx`, `testcontainers[kafka]`, later `pytest-cov`), and migration/seeding tooling (`tqdm`, `python-dotenv`, arguably `alembic`) in its own dependency group — not named `build`, which would read as `[build-system]`.
  3. **Build the project in one command from a clean git clone** (or one per service if needed).
  4. **GitHub Actions runs the tests and analyses test coverage** on commits. No deployment step.
  5. **Smallest reasonable images, security included:** a non-root user in every Dockerfile, no test dependencies in any image, and `migrations/`/`scripts/` plus their tooling moved out of the app image into a separate image used only by the `*_migration`/`*_seed` containers — today the app images carry them for their whole lifetime just to serve the init containers.
  6. **Later, once the map frontend exists** (see Planned Features > Truck position tracking): its own GitHub Actions workflow. Nothing to prepare now beyond keeping each deployable self-contained in its own directory.

  **Design (the uv part is built; the rest is agreed but not built):**
  - **(Done.) uv everywhere, each service a standalone uv project with its own `uv.lock`**, the root `[tool.uv.workspace]` dropped — a uv workspace is one shared environment and one lock for all members, which fought the per-service `.venv` workflow and couldn't work here anyway since every service's package is named `app`. Same two files drive every environment: `uv sync` locally, `uv sync --locked` in CI, and in Docker `uv sync --locked --no-default-groups` (plus `--group tooling` for the tooling target) — not just `--no-dev`, since `default-groups` would otherwise pull `tooling` into the app image too. The lockfile is what makes a clean clone resolve the same versions months later.
  - **One Dockerfile per service with two targets**, selected in `docker-compose.yml` via `build.target`: an app target (production dependencies + `app/` only) and a tooling target (app target + `migrations/`, `scripts/`, `alembic.ini` + the `tooling` group). Dependencies install into a virtualenv at a neutral path (e.g. `/opt/venv`, via `UV_PROJECT_ENVIRONMENT`) instead of `/root/.local`, so a non-root user can read it. The size gain from the split itself is small — it's a tidiness choice; the larger gain is a `.dockerignore` (none exists, so each build sends the service's whole `.venv` as build context). Things to get right: the Dockerfiles' `CMD` can no longer be `fastapi run` (that came from `fastapi[standard]`, now replaced by plain `fastapi` + `uvicorn[standard]`) and must become `uvicorn app.main:app --host 0.0.0.0 --port <port>` — uvicorn binds `127.0.0.1` by default, unlike `fastapi run`; and `infra/k8s/deploy-local.bat` runs `docker build` with no `--target`, which builds the *last* stage in the file, so either the app target goes last or the script gains `--target`. `docker-compose.yml`'s own `--reload` on Fleet/Delivery does nothing (no source volume mounted) and can go at the same time.
  - **Clean-clone setup:** a root `setup.bat` next to `run-tests.bat`, chaining the `.env` bootstrap, `uv sync` per service and `docker compose up --build`.
  - **CI:** one job per service (`uv sync --locked`, then pytest with `pytest-cov`); parallel jobs are fine there since each gets its own runner, unlike the local Kafka container contention.

  **Known gaps found while planning** (to fix as part of this work):
  - **(Fixed.)** The `pyproject.toml` files were not a complete description of what the images need (`tqdm`, `python-dotenv` declared nowhere; `httpx`, `pytest`, `pydantic` only arriving transitively). Every third-party import under `app/`, `scripts/`, `migrations/` and `test/` is now declared explicitly.
  - **(Corrected.)** Fleet's and Delivery's `requirements.txt` list `httpx2`, first written off here as a typo for `httpx`. It isn't: it's the package Starlette's `TestClient` now expects (see Test Conventions > Dependency management). Both files are also UTF-16 with a BOM — moot once they're deleted in phase 2.
  - A fresh clone can't start today: `.env` is git-ignored with no `.env.example`, and there is no `.gitattributes` — with `core.autocrlf=true`, `infra/kafka/create_topics.sh` and `infra/postgres/init-databases.sh` would be checked out with CRLF endings and fail under `sh` in the Linux containers.
  - **(Fixed.)** Stale lockfiles (a root `uv.lock` and per-service ones in Fleet and Delivery, none driving any install): the root one is deleted, and all three services now have a current `uv.lock` that their `.venv` is actually built from.

  **Order:** (1) **done** — dependencies: workspace dropped, the three `pyproject.toml` files reconciled with groups, one `uv.lock` per service; (2) **next** — Dockerfiles: locked install, two targets, non-root user, `.dockerignore`, Compose `build.target`, and deleting the three `requirements.txt` files in the same change (they stay until then so `docker compose up --build` keeps working); (3) clean-clone setup — `.env.example`, `.gitattributes`, `setup.bat`, verified with an actual fresh clone; (4) the CI workflow.
- Add a volume for Kafka too (currently none, flagged by its own `TODO` in `docker-compose.yml`) — separate from the Postgres persistence work above.
- **Add a dedicated end-to-end test tier**, spanning both services, alongside the existing per-service `unit`/`kafka + integration` tests. Motivating gap: every test in the project today (unit and `kafka + integration` alike) is scoped to one service's own code and its own copy of the Kafka message schemas — and Fleet's and Delivery's copies of `TruckAssignmentRequest`/`TruckAssignmentCompleted` are deliberately independent, not shared (see Kafka above). A schema drift between the two (e.g. one side renaming a field) would pass every existing test undetected, since each side only ever checks its own copy against itself — only a real cross-service test can catch that class of bug. Design constraints already identified:
  - Both services' internal package is literally named `app` (`apps/fleet_service/app`, `apps/delivery_service/app`), so a single Python test process can't import both at once — they'd collide. E2E tests are therefore necessarily true black-box tests against real, running HTTP endpoints (via `docker compose up`, or two separately-launched `uvicorn` processes), never in-process imports the way every existing suite works.
  - Likely doesn't need direct DB access or `testcontainers[postgresql]` at all: the API's own documented contract already exposes the eventually-consistent result through the public surface (`POST /trucks` on Fleet, `POST /deliveries` on Delivery, then poll `GET /deliveries/{id}` until it leaves `REQUESTED`) — asserting through that surface is more faithful "black box" testing than reaching into either service's internal schema/DB directly, and sidesteps the package-name collision above entirely.
  - Consumer-driven contract testing (e.g. Pact) was raised as a lighter-weight alternative/complement specifically for the schema-drift risk, without needing to run both services together — noted as probably more infrastructure than this project needs right now, not pursued for now.
  - Not decided yet: exact test folder location (a new top-level folder outside `apps/`, separate from both services' own `test/`, is the likely shape, since it belongs to neither service alone) or CI wiring.

**Later:**
- Malformed messages (pydantic `ValidationError`) on both `truck-assignment-requested` and `truck-assignment-completed` are currently logged and committed (i.e. dropped) rather than routed anywhere — whether a dead-letter topic is needed is still open (flagged by `TODO`s in both consumers)
- An `Assignment` history table in Fleet Service (`delivery_id`, `truck_id`, timestamp, outcome) — today no assignment record is ever persisted, only the resulting `Truck.status` flip (`assignment_repository.py` doesn't store anything, it just queries `truck_repository` live). A history table would enable auditing, and could let `Truck.status` become derived (computed from open/unresolved assignments) instead of stored — at the cost of a more expensive availability query and needing an explicit signal for when an assignment ends, which nothing produces yet
- Monitoring and logging (e.g., Prometheus/Grafana, ELK stack)
- Organize `docker-compose.yml`'s growing container list (~a dozen services now: `fleet_service`, `delivery_service`, `gps_simulator`, `kafka`, `kafka_init`, `redpanda_console`, `postgres`, `postgres_init`) for readability.
- A single, functionality-grouped seed script instead of one per service (floated while discussing `gps_simulator`'s eventual seed data, not started): Fleet's and Delivery's seed scripts already duplicate a hardcoded 50-truck-ID pool between them (`IN_USE_TRUCK_IDS`/`TRUCK_IDS`, kept in sync by hand — see Database seeding above) so Delivery's seeded `assigned_truck_id`s line up with trucks Fleet actually seeds; a third, `gps_simulator`-side seed script for departures would extend that same copy-paste-and-keep-in-sync problem a third way. The alternative — one script seeding a truck + its deliveries + its departure together, grouped by scenario rather than by service — was raised as probably cleaner once `gps_simulator` actually needs seed data, but not attempted yet. Options worth weighing: Compose `profiles` (start subsets, e.g. `--profile kafka` vs. everything), splitting into multiple compose files combined via `-f`, or just better in-file grouping/comments. Leaning toward splitting into multiple files by directory, tentatively something like `apps/`, `init/`, `database/`, `queue/` — open question is whether to group by resource (e.g. `kafka` + `kafka_init` + `redpanda_console` together) or by lifecycle role (all one-shot init jobs together regardless of resource). Not decided yet.
- Add a database UI for manually browsing/querying Postgres content, parallel to Redpanda Console's role for Kafka — candidates raised: pgAdmin (heaviest, full-featured), Adminer (lightweight, generic), pgweb (lightweight, Postgres-only). Would likely connect as `fleetpulse_admin` to browse both `fleet_service` and `delivery_service` from one instance, since it's a human inspection tool rather than a service credential. Not decided yet; likely lands in the `database/` group above once the container reorg above happens.

## Planned Features

### Truck position tracking

**End-to-end flow (design settled through discussion, not yet built):**
1. **(Done.)** `POST /deliveries` — `Delivery.requested_date` is now `requested_datetime`: the time the *client* wants the delivery arrived at `dropoff_location` (not the time the truck departs). Delivery Service still produces `TruckAssignmentRequested` immediately on creation, unchanged.
2. Fleet Service still assigns purely on current availability and marks the truck `IN_USE` — no forward-looking scheduling, and (for now) a truck is never reset back to `AVAILABLE`. This is a **deliberate, temporary simplification**: a truck gets locked for a delivery that might be a month out, even though it won't actually be driving until much closer to that date. Fixing this properly means letting a truck hold multiple future-scheduled deliveries and transition state over time — the same "Availability-aware delivery scheduling" work already parked further down this doc — so for now the divergence is accepted and deferred rather than solved as a prerequisite.
3. **(Done.)** On a successful `TruckAssignmentCompleted`, **Delivery Service itself calls OSRM** to get the route duration between `pickup_location` and `dropoff_location`, computes `departure_time = requested_datetime - duration`, and produces a new, deliberately lightweight Kafka message onto `truck-departure-scheduled` carrying `delivery_id`, `truck_id`, `pickup_location`, `dropoff_location`, `departure_time`. The OSRM call goes through a new `app/clients/osrm_client.py` (async, via `httpx`), against the public OSRM demo server; since OSRM only routes and doesn't geocode, and `pickup_location`/`dropoff_location` on the `Delivery` are still plain city-name strings, the client also carries a hardcoded city-name → coordinates lookup table (`CITY_POS_BY_NAME`, dict-of-dicts `{'lat': ..., 'lon': ...}` rather than a bare tuple, to avoid the order-ambiguity OSRM's own lon/lat API has) scoped to the seed data's cities for now (real addresses/aliases will replace this later).

   **Revised from the original plan: `pickup_location`/`dropoff_location` on the message carry resolved coordinates (a nested `Coordinates{lat, lon}` model), not city-name strings.** The original design called this message "deliberately lightweight... no coordinates," matching the small-JSON-envelope convention of the other two topics. That was revised once it became clear that shipping bare city names would just push a duplicate `CITY_POS_BY_NAME`-equivalent lookup table onto `gps_simulator`, which needs actual coordinates to call OSRM for route geometry in step 4 anyway — OSRM itself never geocodes city names. Resolving coordinates once in Delivery Service, which already owns `osrm_client.get_city_coordinates()`, and shipping the resolved `Coordinates` avoids that duplication entirely. `TruckDepartureScheduled` (`app/models/truck_departure.py`) is the message model.

   Producing the message is a new, separate `producers/departure_producer.py`, not added to the existing `assignment_producer.py` — different topic, different concern (dispatch scheduling vs. assignment). A failed OSRM call (`OSRMRequestFailed`/`UnknownCity`) or produce isn't caught locally by `osrm_client.py` or `departure_producer.py` themselves; the wiring in `delivery_service.py` catches `UnknownCity` (deterministic — a city missing from the table won't fix itself on retry) but deliberately lets `OSRMRequestFailed` (transient — a network blip or OSRM outage) propagate uncaught, so it falls through to the existing offset-commit-based redelivery mechanism rather than being silently dropped (see Kafka > Offset commit contract).

   **Gotcha hit building this:** `departure_time` is a `datetime`, and `kafka_client.py`'s producer value-serializer is a plain `json.dumps`, which can't serialize a live `datetime` object — this is the first message schema in the project to carry a datetime field, since neither existing topic's schema has one. `departure_producer.py` calls `request.model_dump(mode="json")` (Pydantic v2 renders `datetime` as an ISO 8601 string in that mode) rather than the bare `model_dump()` the other two producers use.

   (Open edge case, not addressed yet: nothing currently stops `departure_time` from landing in the past when `requested_datetime` is too soon for the route to be driven in time.)
4. `gps_simulator` — a new service, a bare `asyncio` worker rather than a FastAPI app (no inbound HTTP traffic, nothing calls it). **Scaffolded, consuming `truck-departure-scheduled` end-to-end and persisting it, with tests at every layer (see Architecture > GPS Simulator and Project Status > Done); the OSRM caching call below is still pending.** It exists purely to **mock a physical GPS tracker** for this learning project — in a real fleet, trucks would carry real telematics hardware reporting actual position every ~10s directly onto Kafka, and neither `gps_simulator` nor its OSRM call would exist at all. Consuming the message from step 3, it will persist the delivery (`delivery_id`, `truck_id`, `pickup_location`, `dropoff_location`, `departure_time`) into its own new Postgres database — a DB of its own, following the same per-service-owns-its-data pattern as Fleet/Delivery, so it never needs to query Delivery Service directly. It then makes its **own, separate** call to OSRM to fetch the actual route coordinates and caches them alongside the delivery row.
5. A periodic tick loop in `gps_simulator` (target ~10s–1min) acts only on deliveries whose `departure_time` has already passed — computing a current position from elapsed time along the cached route and producing it onto a new `truck-position-updates` topic — and leaves deliveries scheduled further out untouched in the DB. No separate scheduler/poller component is needed anywhere in this flow: the deferral is handled entirely by this filter, since both the assignment (step 2) and the Kafka handoff (step 3) already happen immediately/synchronously.
6. **Two independent OSRM calls (step 3 and step 4) is intentional, not redundant** — they serve genuinely different responsibilities that would both exist even with real physical trackers: Delivery Service's call is a business/dispatch ETA-planning concern (computing when a truck must leave to honor a promised arrival time), while `gps_simulator`'s call only stands in for what a real device would otherwise just report on its own (actual position), never compute.
7. `tracking_service` — a new FastAPI service, confirmed as the consumer of `truck-position-updates` (not Fleet Service, which stays scoped to truck CRUD + assignment): keeps an in-memory `{truck_id: latest_position}` cache (serves live reads without touching Kafka/DB per request), persists to a repository on a throttle rather than on every message (storage only needs a rough idea of where a truck is, not perfect accuracy), and exposes a WebSocket endpoint so clients get live position pushes.
8. Open design question, deliberately deferred until both services exist: should `gps_simulator` produce directly onto Kafka, or call an HTTP route on `tracking_service` which produces on its behalf?
9. `truck-position-updates` will likely be a compacted topic (`cleanup.policy=compact`, keyed by `truck_id`), since only the latest position matters — unlike the existing two topics, which use default retention.
10. Map UI: a frontend visualizing live truck positions on a map, built once the backend above exists. Mainly for a visual/demo payoff rather than FastAPI/Kafka practice, so it's the last piece, not the first.

Routing: OSRM's public demo server (`router.project-osrm.org`) is the likely choice for both OSRM call sites above, since it needs no API key.

### Truck maintenance
Truck unavailability for a scheduled repair window (`IN_REPAIR` status with a start/end time). Parked for now.

### Availability-aware delivery scheduling
Allow scheduling a delivery on a truck that is currently unavailable but will become available by the delivery time, instead of only considering trucks available right now. Parked as a later task.
