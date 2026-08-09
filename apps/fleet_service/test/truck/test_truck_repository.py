import pytest

from apps.fleet_service.app.models.truck import Truck, TruckStatus
from apps.fleet_service.app.repositories import truck_repository


@pytest.fixture(autouse=True)
def clear_repository():
    truck_repository.clear()

def test_save_truck_stores_truck():
    truck = Truck(
        id="truck-test",
        plate_number="AB-123-CD",
        capacity_kg=1200,
        status=TruckStatus.AVAILABLE,
    )

    truck_repository.save_truck(truck)

    trucks = truck_repository.get_trucks()

    assert trucks == [truck]

def test_get_trucks_by_plate_number():
    plate_number = "AB-123-CD"
    t = truck_repository.get_truck_by_plate_number(plate_number)
    assert t is None

    truck = Truck(
        id="truck-test",
        plate_number="AB-123-CD",
        capacity_kg=1200,
        status=TruckStatus.AVAILABLE,
    )

    truck_repository.save_truck(truck)
    t = truck_repository.get_truck_by_plate_number(plate_number)

    assert t == truck
