from app.clients.kafka_client import get_producer
from app.models.truck_assignment import TruckAssignmentRequest


async def produce_truck_assignment_requested(request: TruckAssignmentRequest) -> None:
    await get_producer().send(
        'truck-assignment-requested',
        key=request.delivery_id,
        value=request.model_dump(),
    )
