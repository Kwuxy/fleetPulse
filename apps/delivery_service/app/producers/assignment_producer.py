import functools
import logging

from app.clients import kafka_client
from app.models.truck_assignment import TruckAssignmentRequest

logger = logging.getLogger(__name__)


async def produce_truck_assignment_requested(request: TruckAssignmentRequest) -> None:
    topic = 'truck-assignment-requested'
    future = await kafka_client.get_producer().send(
        topic,
        key=request.delivery_id,
        value=request.model_dump(),
    )
    future.add_done_callback(functools.partial(kafka_client.log_send_failure, topic, request.delivery_id))
