from fastapi import FastAPI

from services.fleet_service.app.routes import truck_routes, assignment_routes

app = FastAPI(title='Fleet Service')

app.include_router(truck_routes.router)
app.include_router(assignment_routes.router)
