import logging
import os
from fastapi import FastAPI

from app.routes import truck_routes, assignment_routes

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    # format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    format=f"{'%(levelname)s:': <18} %(message)s",
)

app = FastAPI(title='Fleet Service')

app.include_router(truck_routes.router)
app.include_router(assignment_routes.router)
