import logging

from pydantic import ValidationError

from app.clients.kafka_client import QueueMessageStatus
from app.models.truck_assignment import TruckAssignmentCompleted
from app.services import delivery_service
from app.exceptions import NotFoundException

logger = logging.getLogger(__name__)


async def handle_truck_assignment_completed(msg: dict) -> QueueMessageStatus:
    try:
        assignment = TruckAssignmentCompleted(**msg)
    except ValidationError as e:
        # TODO : ValidationError should go to a dead-letter topic
        logger.warning(f'Invalid request: {e}')
        return QueueMessageStatus.CONSUMED

    try:
        await delivery_service.update_delivery_with_truck_assignment(assignment)
    except NotFoundException as e:
        logger.warning(f'Error while consuming truck assignment completed: {e}')
        return QueueMessageStatus.CONSUMED

    return QueueMessageStatus.CONSUMED
