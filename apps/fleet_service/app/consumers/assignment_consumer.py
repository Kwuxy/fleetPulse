import logging

from pydantic import ValidationError

from app.services import assignment_service
from app.clients.kafka_client import QueueMessageStatus
from app.models.assignment import TruckAssignmentRequest, TruckAssignmentCompleted, TruckAssignmentFailureReason
from app.exceptions import UnknownDelivery, InvalidCargoWeight, NoTruckAvailable
from app.producers import assignment_producer

logger = logging.getLogger(__name__)


async def handle_truck_assignment_requested(msg: dict) -> QueueMessageStatus:
    try:
        request = _build_truck_assignment_request(msg)
    except ValidationError as e:
        # TODO : ValidationError should go to a dead-letter topic
        logger.warning(f'Invalid request: {e}')
        return QueueMessageStatus.CONSUMED

    try:
        truck = await assignment_service.assign_truck_to_delivery(request)
        logger.info(f'Assigned truck: {truck.id}')
    except (UnknownDelivery, InvalidCargoWeight) as e:
        logger.warning(f'Truck not assigned, {e}')
        await assignment_producer.produce_truck_assignment_completed(
            TruckAssignmentCompleted.get_failed(
                delivery_id=request.delivery_id,
                reason=TruckAssignmentFailureReason.INVALID_REQUEST,
                description=str(e)
            )
        )
        return QueueMessageStatus.CONSUMED
    except NoTruckAvailable as e:
        logger.warning(f'Truck not assigned, {e}')
        await assignment_producer.produce_truck_assignment_completed(
            TruckAssignmentCompleted.get_failed(
                delivery_id=request.delivery_id,
                reason=TruckAssignmentFailureReason.NO_AVAILABLE_TRUCK,
                description=str(e)
            )
        )
        return QueueMessageStatus.CONSUMED

    await assignment_producer.produce_truck_assignment_completed(
        TruckAssignmentCompleted.get_success(delivery_id=request.delivery_id, truck_id=truck.id)
    )
    return QueueMessageStatus.CONSUMED

def _build_truck_assignment_request(msg: dict) -> TruckAssignmentRequest:
    return TruckAssignmentRequest(**msg)
