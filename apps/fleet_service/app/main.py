import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.routes import truck_routes, assignment_routes
from app.clients import kafka_client
from app.consumers import assignment_consumer

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    # format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    format=f"%(levelname)-8s %(message)s",
)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await kafka_client.start_consuming(assignment_consumer.handle_truck_assignment_requested)
    yield
    await kafka_client.stop_consuming()

app = FastAPI(lifespan=lifespan, title='Fleet Service')

app.include_router(truck_routes.router)
app.include_router(assignment_routes.router)
