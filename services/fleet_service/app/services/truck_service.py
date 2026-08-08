import uuid

from services.fleet_service.app.exceptions import InvalidTruckCapacity, InvalidPlateNumber, DuplicatePlateNumber
from services.fleet_service.app.models.truck import CreateTruckRequest, Truck, TruckStatus
from services.fleet_service.app.repositories import truck_repository


def create_truck(create_truck_request: CreateTruckRequest):
    if not _is_valid_capacity(create_truck_request.capacity_kg):
        raise InvalidTruckCapacity(create_truck_request.capacity_kg)

    if not _is_valid_plate_number(create_truck_request.plate_number):
        raise InvalidPlateNumber(create_truck_request.plate_number)

    if _is_duplicate_plate_number(create_truck_request.plate_number):
        raise DuplicatePlateNumber(create_truck_request.plate_number)

    truck = Truck(
        id=_generate_truck_id(),
        **create_truck_request.model_dump(),
        status=TruckStatus.AVAILABLE
    )

    truck_repository.save_truck(truck)
    return truck

def _generate_truck_id():
    return f"truck-{uuid.uuid4().hex[:8]}"

def _is_valid_plate_number(plate_number: str):
    return True  # TODO : Implement plate number validation

def _is_duplicate_plate_number(plate_number: str):
    return truck_repository.get_truck_by_plate_number(plate_number) is not None

def _is_valid_capacity(capacity_kg: int):
    return capacity_kg > 0

def get_trucks() -> list[Truck]:
    return truck_repository.get_trucks()
