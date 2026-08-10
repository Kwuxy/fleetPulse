### Done project's features
- Fleet microservice
  - Create a truck `POST /trucks`
  - List all trucks `GET /trucks`
  - Assign a truck to a delivery (responsible for choosing the truck) `POST /internal/truck-assignments`
- Delivery microservice
  - Create a delivery `POST /deliveries`

All routes, services and repositories are tests with pytest

### Current working context
- List all deliveries is implemented `GET /deliveries`
- Write tests for list all deliveries
- Get delivery by id and write tests `GET /delivery/{id}`