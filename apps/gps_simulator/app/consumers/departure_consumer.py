import logging

from pydantic import ValidationError

from app.clients.kafka_client import QueueMessageStatus
from app.models.truck_departure import TruckDepartureScheduled
from app.services import journey_service

logger = logging.getLogger(__name__)


async def handle_truck_departure_scheduled(msg: dict) -> QueueMessageStatus:
    try:
        departure = _build_truck_departure_scheduled(msg)
    except ValidationError as e:
        # TODO : ValidationError should go to a dead-letter topic
        logger.warning(f'Invalid request: {e}')
        return QueueMessageStatus.CONSUMED

    await journey_service.create_journey(departure)
    return QueueMessageStatus.CONSUMED

def _build_truck_departure_scheduled(msg: dict) -> TruckDepartureScheduled:
    return TruckDepartureScheduled(**msg)
