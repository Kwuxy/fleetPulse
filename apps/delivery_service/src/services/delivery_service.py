import uuid
from datetime import date

from clients import fleet_client
from exceptions import InvalidClient, SameLocationsException, InvalidCargo, InvalidRequestedDate, NotFoundException
from models.delivery import Delivery, CreateDeliveryRequest, DeliveryStatus
from repositories import delivery_repository


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

    truck_id = await fleet_client.assign_truck_to_delivery(delivery.id, delivery.cargo_weight_kg)
    if truck_id:
        delivery.assigned_truck_id = truck_id
        delivery.status = DeliveryStatus.ASSIGNED
    else:
        delivery.status = DeliveryStatus.DENIED

    delivery_repository.save(delivery)
    return delivery

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
