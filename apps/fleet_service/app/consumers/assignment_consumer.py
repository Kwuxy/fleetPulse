import logging

from pydantic import ValidationError

from app.services import assignment_service
from app.clients.kafka_client import QueueMessageStatus
from app.models.assignment import TruckAssignmentRequest, TruckAssignmentCompleted, TruckAssignmentFailureReason
from app.exceptions import UnknownDelivery, InvalidCargoWeight, NoTruckAvailable

logger = logging.getLogger(__name__)


async def handle_truck_assignment_requested(msg: dict) -> QueueMessageStatus:
    try:
        request = TruckAssignmentRequest(**msg)
        truck = assignment_service.assign_truck_to_delivery(request)
        logger.info(f'Assigned truck: {truck.id}')
    except ValidationError as e:
        # TODO : ValidationError should go to a dead-letter topic
        logger.warning(f'Invalid request: {e}')
        return QueueMessageStatus.CONSUMED
    except (UnknownDelivery, InvalidCargoWeight) as e:
        logger.warning(f'Truck not assigned, {e}')
        produce_truck_assignment_completed(
            TruckAssignmentCompleted.get_failed(reason=TruckAssignmentFailureReason.INVALID_REQUEST)
        )
        return QueueMessageStatus.CONSUMED
    except NoTruckAvailable as e:
        logger.warning(f'Truck not assigned, {e}')
        produce_truck_assignment_completed(
            TruckAssignmentCompleted.get_failed(reason=TruckAssignmentFailureReason.NO_AVAILABLE_TRUCK)
        )
        return QueueMessageStatus.CONSUMED

    # TODO : Add description attribute to TruckAssignmentCompleted & put exception message when failed ?
    # TODO : Add delivery_id to TruckAssignmentCompleted

    produce_truck_assignment_completed(
        TruckAssignmentCompleted.get_success(truck_id=truck.id)
    )
    return QueueMessageStatus.CONSUMED

# TODO : Implement this function & move to producer module
def produce_truck_assignment_completed(truck_assignment_completed: TruckAssignmentCompleted):
    logger.info(f'Producing truck assignment completed: {truck_assignment_completed}')