import pytest

from services.fleet_service.app.exceptions import InvalidTruckCapacity
from services.fleet_service.app.models.truck import CreateTruckRequest, TruckStatus
from services.fleet_service.app.repositories import truck_repository
from services.fleet_service.app.services import truck_service


@pytest.fixture(autouse=True)
def clear_repository():
    truck_repository.clear()

def test_create_truck_creates_available_truck():
    request = CreateTruckRequest(
        plate_number="AB-123-CD",
        capacity_kg=1200,
    )

    truck = truck_service.create_truck(request)

    assert truck.id.startswith("truck-")
    assert truck.plate_number == "AB-123-CD"
    assert truck.capacity_kg == 1200
    assert truck.status == TruckStatus.AVAILABLE


def test_create_truck_rejects_invalid_capacity():
    request = CreateTruckRequest(
        plate_number="AB-123-CD",
        capacity_kg=0,
    )

    with pytest.raises(InvalidTruckCapacity):
        truck_service.create_truck(request)

def test_get_trucks_returns_created_trucks():
    request = CreateTruckRequest(
        plate_number="AB-123-CD",
        capacity_kg=1200,
    )

    created_truck = truck_service.create_truck(request)

    trucks = truck_service.get_trucks()

    assert len(trucks) == 1
    assert trucks[0] == created_truck
