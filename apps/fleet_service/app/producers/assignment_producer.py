from app.clients.kafka_client import get_producer
from app.models.assignment import TruckAssignmentCompleted


async def produce_truck_assignment_completed(truck_assignment_completed: TruckAssignmentCompleted) -> None:
    await get_producer().send(
        'truck-assignment-completed',
        key=truck_assignment_completed.delivery_id,
        value=truck_assignment_completed.model_dump(),
    )
