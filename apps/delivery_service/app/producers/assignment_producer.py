import asyncio
import functools
import logging

from app.clients.kafka_client import get_producer
from app.models.truck_assignment import TruckAssignmentRequest

logger = logging.getLogger(__name__)


async def produce_truck_assignment_requested(request: TruckAssignmentRequest) -> None:
    topic = 'truck-assignment-requested'
    future = await get_producer().send(
        topic,
        key=request.delivery_id,
        value=request.model_dump(),
    )
    future.add_done_callback(functools.partial(_log_send_failure, topic, request.delivery_id))


def _log_send_failure(topic: str, key: str, future: asyncio.Future) -> None:
    exc = future.exception()
    if exc is not None:
        logger.error("Failed to deliver message to %s (key=%s): %s", topic, key, exc, exc_info=exc)
