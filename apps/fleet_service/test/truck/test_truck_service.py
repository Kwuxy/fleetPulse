import pytest

from app.exceptions import InvalidTruckCapacity, DuplicatePlateNumber
from app.models.truck import CreateTruckRequest, TruckStatus
from app.repositories import truck_repository
from app.services import truck_service


@pytest.fixture(autouse=True)
def clear_repository():
    truck_repository.clear()

@pytest.mark.service
@pytest.mark.unit
class TestTruckService:
    def test_create_truck_creates_available_truck(self):
        request = CreateTruckRequest(
            plate_number="AB-123-CD",
            capacity_kg=1200,
        )

        truck = truck_service.create_truck(request)

        assert truck.id.startswith("truck-")
        assert truck.plate_number == "AB-123-CD"
        assert truck.capacity_kg == 1200
        assert truck.status == TruckStatus.AVAILABLE


    def test_create_truck_rejects_invalid_capacity(self):
        request = CreateTruckRequest(
            plate_number="AB-123-CD",
            capacity_kg=0,
        )

        with pytest.raises(InvalidTruckCapacity):
            truck_service.create_truck(request)

    def test_create_truck_rejects_duplicate_plate_number(self):
        request = CreateTruckRequest(
            plate_number="AB-123-CD",
            capacity_kg=1200,
        )

        truck_service.create_truck(request)

        with pytest.raises(DuplicatePlateNumber):
            truck_service.create_truck(request)

    def test_get_trucks_returns_created_trucks(self):
        request = CreateTruckRequest(
            plate_number="AB-123-CD",
            capacity_kg=1200,
        )

        created_truck = truck_service.create_truck(request)

        trucks = truck_service.get_trucks()

        assert len(trucks) == 1
        assert trucks[0] == created_truck
