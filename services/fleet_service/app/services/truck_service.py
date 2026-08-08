import uuid

from services.fleet_service.app.exceptions import InvalidTruckCapacity, InvalidPlateNumber
from services.fleet_service.app.models.truck import CreateTruckRequest, Truck, TruckStatus

trucks: dict[str, Truck] = {}


def create_truck(create_truck_request: CreateTruckRequest):
    if not _is_valid_capacity(create_truck_request.capacity_kg):
        raise InvalidTruckCapacity(create_truck_request.capacity_kg)

    if not _is_valid_plate_number(create_truck_request.plate_number):
        raise InvalidPlateNumber(create_truck_request.plate_number)

    # Should validate plate number uniqueness here

    truck = Truck(
        id=_generate_truck_id(),
        **create_truck_request.model_dump(),
        status=TruckStatus.AVAILABLE
    )

    trucks[truck.id] = truck

    return truck

def _generate_truck_id():
    return f"truck-{uuid.uuid4().hex[:8]}"

def _is_valid_plate_number(plate_number: str):
    return True  # TODO : Implement plate number validation

def _is_valid_capacity(capacity_kg: int):
    return capacity_kg > 0

def get_trucks() -> list[Truck]:
    return list(trucks.values())
