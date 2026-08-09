# FleetPulse

FleetPulse is a learning project built to explore microservices architecture, event-driven programming with Kafka, Docker containerization, and FastAPI API development.

The project models a delivery fleet management system where trucks can be registered, assigned to deliveries, and eventually sent to repair. The goal is to grow the application incrementally from a small FastAPI service into a dockerized, event-driven microservices system.

## Current Status

The project currently contains the first service: the **Fleet Service**.

The Fleet Service can:

- create trucks
- list registered trucks
- store truck data in memory

More services and infrastructure will be added progressively.

## Run the Project
### 1. Install dependencies

From the Fleet Service directory:
```bash
cd services/fleet_service
```

Install the project dependencies using the configured Python environment:
```bash
pip install -e .
```

### 2. Start the Fleet Service
From the project root, run:
```bash
uvicorn apps.fleet_service.app.main:app --reload --port 8001
```

The Fleet Service will be available at:
```text
http://localhost:8001
```

### 3. Test the Fleet Service
FastAPI automatically exposes interactive API documentation at:
```text
http://localhost:8001/docs
```

A Bruno collection of API calls can be found in the `api_collection` directory and can be imported.
