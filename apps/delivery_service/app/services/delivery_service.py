import uuid
from datetime import date

from app.producers import assignment_producer
from app.exceptions import InvalidClient, SameLocationsException, InvalidCargo, InvalidRequestedDate, NotFoundException
from app.models.delivery import Delivery, CreateDeliveryRequest, DeliveryStatus
from app.repositories import delivery_repository
from app.models.truck_assignment import TruckAssignmentCompleted, TruckAssignmentRequest


async def create_delivery(request: CreateDeliveryRequest) -> Delivery:
    if not _client_exist(request.client_id):
        raise InvalidClient(request.client_id)

    if not _locations_are_different(request.pickup_location, request.dropoff_location):
        raise SameLocationsException()

    if not _cargo_is_valid(request.cargo_weight_kg):
        raise InvalidCargo(request.cargo_weight_kg)

    if not _date_is_valid(request.requested_date):
        raise InvalidRequestedDate(request.requested_date)

    delivery = Delivery(
        id=_generate_delivery_id(),
        **request.model_dump(),
        status=DeliveryStatus.REQUESTED,
        assigned_truck_id=None
    )

    delivery_repository.save(delivery)

    assignment_request = TruckAssignmentRequest(delivery_id=delivery.id, cargo_weight_kg=delivery.cargo_weight_kg)
    await assignment_producer.produce_truck_assignment_requested(assignment_request)
    return delivery

def update_delivery_with_truck_assignment(assignment: TruckAssignmentCompleted) -> None:
    delivery = get_delivery_by_id(assignment.delivery_id)
    delivery.assigned_truck_id = assignment.truck_id
    delivery.status = DeliveryStatus.ASSIGNED if assignment.assigned else DeliveryStatus.DENIED
    delivery_repository.save(delivery)

def _client_exist(client_id: int) -> bool:
    return True

def _locations_are_different(pickup_location: str, dropoff_location: str) -> bool:
    return pickup_location != dropoff_location

def _cargo_is_valid(cargo_weight_kg: int) -> bool:
    return cargo_weight_kg > 0

def _date_is_valid(requested_date: date) -> bool:
    return requested_date > date.today()

def _generate_delivery_id():
    return f"delivery-{uuid.uuid4().hex[:8]}"

def get_deliveries() -> list[Delivery]:
    return delivery_repository.get_deliveries()

def get_delivery_by_id(delivery_id: str) -> Delivery:
    delivery = delivery_repository.get_delivery_by_id(delivery_id)
    if not delivery:
        raise NotFoundException(delivery_id)

    return delivery
