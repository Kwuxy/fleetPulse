# 🚀 FleetPulse Local Development Setup

## Prerequisites
- Docker Desktop installed and running (with Kubernetes enabled)
- kubectl CLI available
- PyCharm or other IDE

## One-Click Deployment

### Option 1: PyCharm Run Configuration (Recommended)
1. Open PyCharm
2. Look for the **🚀 Deploy FleetPulse Local** run configuration in the top right
3. Click the green **Run** button
4. Wait for services to deploy (~30-60 seconds)

### Option 2: Manual Batch Script
```bash
./deploy-local.bat
```

## What Happens
1. ✅ Builds Docker images for both services
2. ✅ Deploys to local Kubernetes
3. ✅ Waits for pods to be ready
4. ✅ Starts port forwarding automatically

## Access Your Services
- **Fleet Service:** http://localhost:8001
- **Delivery Service:** http://localhost:8002
- **API Docs (FastAPI):**
  - Fleet: http://localhost:8001/docs
  - Delivery: http://localhost:8002/docs

## Stopping the Deployment
- In PyCharm: Click the red Stop button
- Manual: Close the command windows or press Ctrl+C

## Troubleshooting

### Services won't start
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

### Port already in use
```bash
# Windows: Kill processes using port 8001/8002
netstat -ano | findstr :8001
taskkill /PID <PID> /F
```

### Docker image build fails
- Ensure `requirements.txt` exists in each service directory
- Check that `app/main.py` is present in each service

## Development Workflow
1. Make changes to your FastAPI code in `apps/fleet_service/app/` or `apps/delivery_service/app/`
2. Click Run again to rebuild and redeploy
3. Services will be available immediately after pod readiness

---

For questions, see the root README.md or ask your team lead.
