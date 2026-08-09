import pytest

from apps.fleet_service.app.models.truck import Truck, TruckStatus
from apps.fleet_service.app.repositories import assignment_repository, truck_repository


@pytest.fixture(autouse=True)
def clear_repository():
    truck_repository.clear()


@pytest.mark.repository
@pytest.mark.unit
class TestAssignmentRepository:
    def test_find_available_truck_for_capacity_returns_smallest_sufficient_truck(self):
        large_truck = Truck(
            id="truck-large",
            plate_number="AA-111-AA",
            capacity_kg=3000,
            status=TruckStatus.AVAILABLE,
        )
        medium_truck = Truck(
            id="truck-medium",
            plate_number="BB-222-BB",
            capacity_kg=1200,
            status=TruckStatus.AVAILABLE,
        )
        smallest_sufficient_truck = Truck(
            id="truck-small",
            plate_number="CC-333-CC",
            capacity_kg=800,
            status=TruckStatus.AVAILABLE,
        )

        truck_repository.save_truck(large_truck)
        truck_repository.save_truck(medium_truck)
        truck_repository.save_truck(smallest_sufficient_truck)

        truck = assignment_repository.find_available_truck_for_capacity(700)

        assert truck == smallest_sufficient_truck

    def test_find_available_truck_for_capacity_ignores_trucks_with_insufficient_capacity(self):
        insufficient_truck = Truck(
            id="truck-small",
            plate_number="AA-111-AA",
            capacity_kg=500,
            status=TruckStatus.AVAILABLE,
        )
        sufficient_truck = Truck(
            id="truck-large",
            plate_number="BB-222-BB",
            capacity_kg=1000,
            status=TruckStatus.AVAILABLE,
        )

        truck_repository.save_truck(insufficient_truck)
        truck_repository.save_truck(sufficient_truck)

        truck = assignment_repository.find_available_truck_for_capacity(700)

        assert truck == sufficient_truck

    def test_find_available_truck_for_capacity_ignores_trucks_in_use(self):
        in_use_truck = Truck(
            id="truck-in-use",
            plate_number="AA-111-AA",
            capacity_kg=1000,
            status=TruckStatus.IN_USE,
        )
        available_truck = Truck(
            id="truck-available",
            plate_number="BB-222-BB",
            capacity_kg=1200,
            status=TruckStatus.AVAILABLE,
        )

        truck_repository.save_truck(in_use_truck)
        truck_repository.save_truck(available_truck)

        truck = assignment_repository.find_available_truck_for_capacity(700)

        assert truck == available_truck

    def test_find_available_truck_for_capacity_ignores_trucks_in_repair(self):
        in_repair_truck = Truck(
            id="truck-in-repair",
            plate_number="AA-111-AA",
            capacity_kg=1000,
            status=TruckStatus.IN_REPAIR,
        )
        available_truck = Truck(
            id="truck-available",
            plate_number="BB-222-BB",
            capacity_kg=1200,
            status=TruckStatus.AVAILABLE,
        )

        truck_repository.save_truck(in_repair_truck)
        truck_repository.save_truck(available_truck)

        truck = assignment_repository.find_available_truck_for_capacity(700)

        assert truck == available_truck

    def test_find_available_truck_for_capacity_returns_none_when_no_truck_is_available(self):
        truck = Truck(
            id="truck-in-use",
            plate_number="AA-111-AA",
            capacity_kg=1000,
            status=TruckStatus.IN_USE,
        )

        truck_repository.save_truck(truck)

        result = assignment_repository.find_available_truck_for_capacity(700)

        assert result is None