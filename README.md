# FleetPulse

**An event-driven microservices backend for a delivery fleet — trucks, deliveries, and (soon) live GPS tracking simulation — built with FastAPI, Kafka and PostgreSQL.**

![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![Kafka](https://img.shields.io/badge/Apache%20Kafka-KRaft-231F20?logo=apachekafka&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker%20Compose-2496ED?logo=docker&logoColor=white)
![Kubernetes](https://img.shields.io/badge/Kubernetes-local-326CE5?logo=kubernetes&logoColor=white)

FleetPulse models the backend of a logistics company: clients book deliveries, the system finds a truck able to carry the load, plans when it must leave to arrive on time, and simulates its journey. It is a personal project I use to practise the architecture and tooling of production microservice systems — asynchronous messaging, per-service data ownership, containerised infrastructure and a layered testing strategy — end to end, on a realistic domain.

---

## How it works

```mermaid
flowchart LR
    Client([Client / API consumer])

    subgraph Delivery["Delivery Service · FastAPI"]
        D[(Postgres<br/>delivery_service)]
    end
    subgraph Fleet["Fleet Service · FastAPI"]
        F[(Postgres<br/>fleet_service)]
    end
    subgraph GPS["GPS Simulator · asyncio worker"]
        G[(Postgres<br/>gps_simulator)]
    end

    OSRM[[OSRM routing API]]

    Client -- "POST /deliveries" --> Delivery
    Client -- "POST /trucks" --> Fleet
    Delivery -- "truck-assignment-requested" --> Fleet
    Fleet -- "truck-assignment-completed" --> Delivery
    Delivery -- "get route duration" --> OSRM
    Delivery -- "truck-departure-scheduled" --> GPS
```

1. A client creates a delivery. **Delivery Service** stores it as `REQUESTED`, publishes a request on Kafka and answers immediately — the API is *eventually consistent*.
2. **Fleet Service** consumes the request, picks an available truck with enough capacity, and publishes the outcome (`ASSIGNED` or `DENIED` with a reason).
3. Delivery Service updates the delivery. On success, it asks the **OSRM** routing engine how long the trip takes, computes when the truck must leave, and publishes a departure event.
4. **GPS Simulator** consumes departure events and will simulate each truck driving its real road route, stepping through OSRM segment timings to publish realistic positions *(in progress)*.

The services never call each other over HTTP: Kafka is the only integration channel, and each service owns its own database.

## Tech stack

| Area | Tools |
|---|---|
| Services | Python 3.14, FastAPI, Pydantic v2, asyncio |
| Messaging | Apache Kafka (KRaft), aiokafka, Redpanda Console |
| Persistence | PostgreSQL, SQLAlchemy 2 (async, asyncpg), Alembic migrations |
| External APIs | OSRM routing via httpx |
| Testing | pytest, pytest-asyncio, Testcontainers (Kafka & Postgres), respx |
| Infrastructure | Docker, Docker Compose, Kubernetes (local), uv workspace |

## Engineering highlights

- **Reliable message handling.** Consumers commit Kafka offsets manually, only once a message is fully processed — at-least-once delivery. Business rejections (unknown delivery, overweight cargo, no truck available) are resolved into an explicit `DENIED` outcome, while transient failures (e.g. OSRM outage) are left uncommitted so the message is redelivered. No request can get stuck silently.
- **Loosely coupled services.** Each service has its own database, its own user, and its own copy of the message schemas — no shared code or shared tables between services.
- **Layered architecture.** `routes / consumers → services → repositories → models` in every service, keeping business logic independent of HTTP and Kafka.
- **Testing pyramid.**
  - *Unit* tests for routes, services, producers and consumers with mocked collaborators.
  - *Integration* tests against real, disposable Kafka brokers and Postgres databases spun up by Testcontainers, covering redelivery after a crash, malformed messages and every denial path.
- **One-command, reproducible environment.** `docker compose up` starts Kafka, Postgres, idempotent topic/database bootstrapping, migrations, seed data and all services in the right order via health checks and dependency conditions.
- **Graceful shutdown** implemented by hand in the non-HTTP worker (cross-platform signal handling on Linux containers and Windows hosts).

## Project status

| Component | Status |
|---|---|
| Fleet Service — truck management & assignment | ✅ Done |
| Delivery Service — deliveries, assignment flow, departure planning with OSRM | ✅ Done |
| Postgres persistence, Alembic migrations, seeding | ✅ Done |
| Docker Compose & local Kubernetes deployment | ✅ Done |
| GPS Simulator — departure consumption | ✅ Done |
| GPS Simulator — persistence & route simulation | 🚧 In progress |

**Next on the roadmap:** a `tracking_service` exposing live truck positions over WebSockets, a cross-service end-to-end test suite, observability (Prometheus/Grafana), and a map UI.

## Getting started

**Prerequisites:** Docker Desktop.

1. Create a `.env` file at the repository root with the database credentials:

   ```dotenv
   POSTGRES_HOST=postgres
   POSTGRES_PORT=5432
   POSTGRES_ADMIN_USER=fleetpulse_admin
   POSTGRES_ADMIN_PASSWORD=change-me

   FLEET_SERVICE_DB_USER=fleet_service
   FLEET_SERVICE_DB_PASSWORD=change-me
   FLEET_SERVICE_DB_NAME=fleet_service

   DELIVERY_SERVICE_DB_USER=delivery_service
   DELIVERY_SERVICE_DB_PASSWORD=change-me
   DELIVERY_SERVICE_DB_NAME=delivery_service

   GPS_SIMULATOR_DB_USER=gps_simulator
   GPS_SIMULATOR_DB_PASSWORD=change-me
   GPS_SIMULATOR_DB_NAME=gps_simulator
   ```

2. Start the whole stack:

   ```bash
   docker compose up --build
   ```

3. Explore:

   | URL | What |
   |---|---|
   | http://localhost:8001/docs | Fleet Service — interactive API docs |
   | http://localhost:8002/docs | Delivery Service — interactive API docs |
   | http://localhost:8080 | Redpanda Console — browse Kafka topics and messages |

   Try creating a delivery on port 8002, then fetch it again a moment later to see it move from `REQUESTED` to `ASSIGNED`. A ready-to-use [Bruno](https://www.usebruno.com/) collection is available in [`api_collection/`](api_collection).

Kubernetes deployment and more options are described in [`infra/DEPLOYMENT.md`](infra/DEPLOYMENT.md).

## Running the tests

Each service has its own virtual environment. From a service directory:

```bash
cd apps/delivery_service
.venv/Scripts/python.exe -m pytest test -q                                   # everything (requires Docker)
.venv/Scripts/python.exe -m pytest test -m unit                              # fast, no external dependency
```

Or run both main services' suites sequentially from the root with `./run-tests.bat`.

## Repository layout

```
apps/
  fleet_service/      # trucks & assignment (FastAPI)
  delivery_service/   # deliveries, assignment flow, departure planning (FastAPI)
  gps_simulator/      # truck GPS simulation (asyncio worker)
infra/
  kafka/              # topic creation script
  postgres/           # per-service database/user bootstrap
  k8s/                # local Kubernetes deploy/teardown scripts
api_collection/       # Bruno API collection
docker-compose.yml    # full local stack
```
