# 🚀 FleetPulse Local Development Setup

FleetPulse can be run locally two ways: **Docker Compose** (fast, minimal setup, hot-reload) or **Kubernetes** (mirrors the target production-like setup). Use Docker Compose for day-to-day development; use Kubernetes when you need to test the K8s manifests themselves.

## Option A: Docker Compose (Recommended for daily dev)

### Prerequisites
- Docker Desktop installed and running (Kubernetes does **not** need to be enabled)

### Start the services
```bash
docker compose up --build
```
- `--build` rebuilds the images; drop it on subsequent runs if the code hasn't changed dependencies.
- Add `-d` to run in the background.

### Stop the services
```bash
docker compose down
```

### What Happens
1. ✅ Builds an image for each service from its `Dockerfile`
2. ✅ Starts both containers with `uvicorn --reload`
3. ✅ Mounts each service's `app/` directory as a volume, so code edits reload automatically — no rebuild needed
4. ✅ Starts a local Kafka broker (KRaft mode) plus a one-shot `kafka_init` service that creates the two truck-assignment topics, and points both app services at it via `KAFKA_BOOTSTRAP_SERVERS` — Fleet Service and Delivery Service communicate with each other asynchronously through Kafka

### Useful commands
```bash
docker compose logs -f              # tail logs from both services
docker compose logs -f delivery_service
docker compose ps                   # check container status
docker compose up --build --force-recreate  # rebuild from scratch
```

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
1. ✅ Builds Docker images for both services
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
- Ensure `requirements.txt` exists in each service directory
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
