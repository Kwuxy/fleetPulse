import uuid
from datetime import datetime

from app.producers import assignment_producer, departure_producer
from app.exceptions import InvalidClient, SameLocationsException, InvalidCargo, InvalidRequestedDate, NotFoundException, \
    UnassignedTruckOnCompletedAssignment
from app.models.delivery import Delivery, CreateDeliveryRequest, DeliveryStatus
from app.repositories import delivery_repository
from app.models.truck_assignment import TruckAssignmentCompleted, TruckAssignmentRequest
from app.models.truck_departure import TruckDepartureScheduled, Coordinates
from app.clients import osrm_client


async def create_delivery(request: CreateDeliveryRequest) -> Delivery:
    if not _client_exist(request.client_id):
        raise InvalidClient(request.client_id)

    if not _locations_are_different(request.pickup_location, request.dropoff_location):
        raise SameLocationsException()

    if not _cargo_is_valid(request.cargo_weight_kg):
        raise InvalidCargo(request.cargo_weight_kg)

    if not _date_is_valid(request.requested_datetime):
        raise InvalidRequestedDate(request.requested_datetime)

    delivery = Delivery(
        id=_generate_delivery_id(),
        **request.model_dump(),
        status=DeliveryStatus.REQUESTED,
        assigned_truck_id=None
    )

    await delivery_repository.save_delivery(delivery)

    assignment_request = TruckAssignmentRequest(delivery_id=delivery.id, cargo_weight_kg=delivery.cargo_weight_kg)
    await assignment_producer.produce_truck_assignment_requested(assignment_request)
    return delivery

async def update_delivery_with_truck_assignment(assignment: TruckAssignmentCompleted) -> None:
    delivery = await get_delivery_by_id(assignment.delivery_id)
    delivery.assigned_truck_id = assignment.truck_id
    if assignment.assigned:
        delivery.status = DeliveryStatus.ASSIGNED
    else:
        delivery.status = DeliveryStatus.DENIED
        delivery.denial_reason = assignment.reason
        delivery.denial_description = assignment.description

    await delivery_repository.save_delivery(delivery)

    if not assignment.assigned:
        return

    await _call_truck_departure_scheduled(delivery)

async def _call_truck_departure_scheduled(delivery: Delivery) -> None:
    if delivery.assigned_truck_id is None:
        raise UnassignedTruckOnCompletedAssignment(delivery.id)

    departure_time = delivery.requested_datetime - await osrm_client.get_route_duration(delivery.pickup_location, delivery.dropoff_location)
    request = TruckDepartureScheduled(
        delivery_id=delivery.id,
        truck_id=delivery.assigned_truck_id,
        pickup_location=Coordinates(**osrm_client.get_city_coordinates(delivery.pickup_location)),
        dropoff_location=Coordinates(**osrm_client.get_city_coordinates(delivery.dropoff_location)),
        departure_time=departure_time,
    )
    await departure_producer.produce_truck_departure_scheduled(request)

def _client_exist(client_id: int) -> bool:
    return True

def _locations_are_different(pickup_location: str, dropoff_location: str) -> bool:
    return pickup_location != dropoff_location

def _cargo_is_valid(cargo_weight_kg: int) -> bool:
    return cargo_weight_kg > 0

def _date_is_valid(requested_datetime: datetime) -> bool:
    return requested_datetime > datetime.today()

def _generate_delivery_id():
    return f"delivery-{uuid.uuid4().hex[:8]}"

async def get_deliveries() -> list[Delivery]:
    return await delivery_repository.get_deliveries()

async def get_delivery_by_id(delivery_id: str) -> Delivery:
    delivery = await delivery_repository.get_delivery_by_id(delivery_id)
    if not delivery:
        raise NotFoundException(delivery_id)

    return delivery
