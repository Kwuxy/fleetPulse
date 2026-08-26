import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from app.routes import delivery_routes
from app.clients import kafka_client

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    # format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    format=f"%(levelname)-8s %(message)s",
)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await kafka_client.start_producer()
    yield
    await kafka_client.stop_producer()

app = FastAPI(lifespan=lifespan, title='Delivery Service')

app.include_router(delivery_routes.router)
