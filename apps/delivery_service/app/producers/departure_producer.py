import asyncio
import logging

from app.models.truck_departure import TruckDepartureScheduled

logger = logging.getLogger(__name__)


async def produce_truck_departure_scheduled(request: TruckDepartureScheduled) -> None:
    pass

def _log_send_failure(topic: str, key: str, future: asyncio.Future) -> None:
    exc = future.exception()
    if exc is not None:
        logger.error("Failed to deliver message to %s (key=%s): %s", topic, key, exc, exc_info=exc)
