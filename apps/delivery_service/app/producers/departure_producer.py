import functools
import logging

from app.models.truck_departure import TruckDepartureScheduled
from app.clients import kafka_client

logger = logging.getLogger(__name__)


async def produce_truck_departure_scheduled(request: TruckDepartureScheduled) -> None:
    topic = 'truck-departure-scheduled'
    future = await kafka_client.get_producer().send(
        topic,
        key=request.delivery_id,
        value=request.model_dump(mode="json"),
    )
    future.add_done_callback(functools.partial(kafka_client.log_send_failure, topic, request.delivery_id))
