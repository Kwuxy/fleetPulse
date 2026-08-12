### Done project's features
- Fleet microservice
  - Create a truck `POST /trucks`
  - List all trucks `GET /trucks`
  - Assign a truck to a delivery (responsible for choosing the truck) `POST /internal/truck-assignments`
- Delivery microservice
  - Create a delivery `POST /deliveries`
  - List all deliveries `GET /deliveries`
  - Get delivery by id `GET /delivery/{id}`

All routes, services, and repositories are tested with pytest

### Current working context
- Create Dockerfiles for both services: fleet_service and delivery_service
- Optimize Docker images for smaller size and faster startup times. (multistage builds, caching, etc.)

### Next tasks
- Use docker-compose to define and run multiple containers as a single application.
- Kafka integration for asynchronous communication between services (setup topics, producers, and consumers)
- Update Docker images and docker-compose file to include Kafka service
- Write integration tests for Kafka interactions
- Set up monitoring and logging tools (e.g., Grafana, Prometheus, ELK stack)
- Automate CI/CD pipeline with automated testing and deployment