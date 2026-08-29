import asyncio
import functools
import logging

from app.clients.kafka_client import get_producer
from app.models.assignment import TruckAssignmentCompleted

logger = logging.getLogger(__name__)


async def produce_truck_assignment_completed(truck_assignment_completed: TruckAssignmentCompleted) -> None:
    topic = 'truck-assignment-completed'
    future = await get_producer().send(
        topic,
        key=truck_assignment_completed.delivery_id,
        value=truck_assignment_completed.model_dump(),
    )
    future.add_done_callback(functools.partial(_log_send_failure, topic, truck_assignment_completed.delivery_id))


def _log_send_failure(topic: str, key: str, future: asyncio.Future) -> None:
    exc = future.exception()
    if exc is not None:
        logger.error("Failed to deliver message to %s (key=%s): %s", topic, key, exc, exc_info=exc)
