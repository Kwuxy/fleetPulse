# 🚀 FleetPulse Local Development Setup

FleetPulse can be run locally two ways: **Docker Compose** (fast, minimal setup, hot-reload) or **Kubernetes** (mirrors the target production-like setup). Use Docker Compose for day-to-day development; use Kubernetes when you need to test the K8s manifests themselves.

## Option A: Docker Compose (Recommended for daily dev)

### Prerequisites
- Docker Desktop installed and running (Kubernetes does **not** need to be enabled)
- [uv](https://docs.astral.sh/uv/) installed machine-wide, for the local virtual environments (tests, IDE). The images install their own copy, so Docker alone is enough to just run the stack.
- A `.env` file at the repository root. `setup.bat` creates it from `.env.example`; by hand, copy that file to `.env`.

### First time, from a clean clone
```bat
setup.bat
```
Checks the prerequisites, creates `.env` if missing (never overwrites one), runs `uv sync --locked` in each service, then `docker compose up --build -d`. Safe to run again at any time.

### Start the services
```bash
docker compose up --build
```
- `--build` rebuilds the images; drop it on subsequent runs if neither a `Dockerfile` nor a service's `pyproject.toml`/`uv.lock` changed.
- Add `-d` to run in the background.

### Stop the services
```bash
docker compose down
```

### What Happens
1. ✅ Builds two images per service from its `Dockerfile`: an `app` image for the service itself and a `tooling` image for its migration and seed jobs (see [Dependencies and images](#dependencies-and-images))
2. ✅ Starts a local Kafka broker (KRaft mode) plus a one-shot `kafka_init` job that creates the three topics, and a Postgres server plus a one-shot `postgres_init` job that creates one database and one user per service
3. ✅ Runs each service's `*_migration` job (`alembic upgrade head`), then its `*_seed` job — the databases are wiped and reseeded on every start
4. ✅ Starts Fleet Service and Delivery Service with `uvicorn --reload`, and the GPS Simulator worker, each only once its own jobs have completed
5. ✅ Mounts each service's `app/` directory as a volume, so code edits reload automatically — no rebuild needed (the GPS Simulator has no reloader: `docker compose restart gps_simulator` picks up edits)
6. ✅ Starts Redpanda Console on http://localhost:8080 to browse Kafka topics and messages

### Useful commands
```bash
docker compose logs -f              # tail logs from every container
docker compose logs -f delivery_service
docker compose ps -a                # check container status; -a also lists the finished one-shot jobs (expect Exited (0))
docker compose up --build --force-recreate  # rebuild from scratch
docker compose down -v              # also delete the Postgres volume (needed after changing credentials in .env)
```

### Changing credentials
`postgres_init` only sets a password when it *creates* a user. If you change a password in `.env` while the `postgres_data` volume already exists, the user keeps its old password and the services fail to authenticate. Run `docker compose down -v` first so the users are recreated — the data is reseeded on start anyway.

## Dependencies and images

Each service declares its dependencies **once**, in its own `pyproject.toml`, with exact versions pinned in the `uv.lock` next to it. There is no `requirements.txt` any more: the local virtual environment and the Docker images are both built from those two files with [uv](https://docs.astral.sh/uv/), so they can't drift apart.

### Three sets of dependencies per service

| Where in `pyproject.toml` | What | Local `.venv` | `app` image | `tooling` image |
|---|---|---|---|---|
| `[project].dependencies` | What the running service needs (FastAPI, uvicorn, aiokafka, SQLAlchemy, asyncpg, ...) | ✅ | ✅ | ✅ |
| `tooling` dependency group | Migrations and seeding (Alembic, python-dotenv, tqdm) | ✅ | ❌ | ✅ |
| `dev` dependency group | Tests (pytest, pytest-asyncio, Testcontainers, respx, ...) | ✅ | ❌ | ❌ |

### Day-to-day commands (from inside a service directory)

```bash
uv sync                              # create/update .venv from pyproject.toml + uv.lock (all three sets)
uv add <package>                     # add a production dependency
uv add --group tooling <package>     # add a migration/seeding dependency
uv add --dev <package>               # add a test dependency
uv lock --upgrade-package <package>  # move one package to its newest allowed version
uv run pytest test -q                # run something inside the service's .venv
```

`uv add` updates `pyproject.toml`, `uv.lock` and the `.venv` together. Commit `uv.lock` with every dependency change, then rebuild the images (`docker compose up --build`). Versions never move on their own: a rebuild installs exactly what the lockfile says until you run `uv lock --upgrade` yourself.

### How the images are built

Every `Dockerfile` has the same five stages:

| Stage | Purpose |
|---|---|
| `builder` | Installs the production dependencies into a virtual environment at `/opt/venv` with `uv sync --locked --no-default-groups` |
| `builder_tooling` | Adds the `tooling` group to that environment |
| `runtime` | Clean `python:3.14-slim` image with a non-root user, the production environment and `app/` |
| `tooling` | `runtime` plus the tooling environment, `migrations/`, `scripts/` and `alembic.ini` |
| `app` | An alias of `runtime`, kept last so a plain `docker build` produces the application image |

`docker-compose.yml` selects a stage per container with `build.target`: `app` for the three services, `tooling` for the `*_migration` and `*_seed` jobs. As a result the application images contain no test tooling, no Alembic and no seed scripts, and every container runs as an unprivileged user (`appuser`).

`--locked` makes a build fail if `uv.lock` is out of date with `pyproject.toml`, instead of silently installing versions nobody tested. If that happens, run `uv lock` in the service directory and commit the result.

## Option B: Kubernetes

### Prerequisites
- Docker Desktop installed and running (with Kubernetes enabled)
- kubectl CLI available
- PyCharm or other IDE

### One-Click Deployment

#### Option 1: PyCharm Run Configuration (Recommended)
1. Open PyCharm
2. Look for the **🚀 Deploy FleetPulse Local** run configuration in the top right
3. Click the green **Run** button
4. Wait for services to deploy (~30-60 seconds)

#### Option 2: Manual Batch Script
```bash
./infra/k8s/deploy-local.bat
```

### What Happens
1. ✅ Builds Docker images for Fleet Service and Delivery Service — `docker build` with no target, which yields each `Dockerfile`'s last stage, the `app` image
2. ✅ Deploys to local Kubernetes
3. ✅ Waits for pods to be ready
4. ✅ Starts port forwarding automatically

### Stopping the Deployment
```bash
./infra/k8s/shutdown-local.bat
```
Or, in PyCharm: click the red Stop button.

### Troubleshooting

#### Services won't start
```bash
# Check pod status
kubectl get pods

# View logs
kubectl logs deployment/fleet-deployment
kubectl logs deployment/delivery-deployment

# Reset everything
kubectl delete deployment fleet-deployment delivery-deployment
kubectl delete service fleet-service delivery-service
```

#### Port already in use
```bash
# Windows: Kill processes using port 8001/8002
netstat -ano | findstr :8001
taskkill /PID <PID> /F
```

#### Docker image build fails
- An error saying *The lockfile at uv.lock needs to be updated, but --locked was provided*: `pyproject.toml` changed without its lockfile. Run `uv lock` in that service directory and commit `uv.lock`.
- Ensure `pyproject.toml` and `uv.lock` both exist in each service directory
- Check that `app/main.py` is present in each service

### Development Workflow
1. Make changes to your FastAPI code in `apps/fleet_service/app/` or `apps/delivery_service/app/`
2. Click Run again to rebuild and redeploy
3. Services will be available immediately after pod readiness

## Access Your Services

Both options expose the services on the same ports:
- **Fleet Service:** http://localhost:8001
- **Delivery Service:** http://localhost:8002
- **API Docs (FastAPI):**
  - Fleet: http://localhost:8001/docs
  - Delivery: http://localhost:8002/docs

---

For questions, see the root README.md or ask your team lead.
