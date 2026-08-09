import pytest

from apps.fleet_service.app.exceptions import InvalidCargoWeight, NoTruckAvailable
from apps.fleet_service.app.models.assignment import TruckAssignmentRequest
from apps.fleet_service.app.models.truck import Truck, TruckStatus
from apps.fleet_service.app.repositories import truck_repository
from apps.fleet_service.app.services import assignment_service


@pytest.fixture(autouse=True)
def clear_repository():
    truck_repository.clear()


@pytest.mark.service
@pytest.mark.unit
class TestAssignmentService:
    def test_assign_truck_to_delivery_assigns_smallest_sufficient_available_truck(self):
        large_truck = Truck(
            id="truck-large",
            plate_number="AA-111-AA",
            capacity_kg=3000,
            status=TruckStatus.AVAILABLE,
        )
        smallest_sufficient_truck = Truck(
            id="truck-small",
            plate_number="BB-222-BB",
            capacity_kg=800,
            status=TruckStatus.AVAILABLE,
        )

        truck_repository.save_truck(large_truck)
        truck_repository.save_truck(smallest_sufficient_truck)

        request = TruckAssignmentRequest(
            delivery_id="delivery-123",
            cargo_weight_kg=700,
        )

        assigned_truck = assignment_service.assign_truck_to_delivery(request)

        assert assigned_truck.id == "truck-small"
        assert assigned_truck.status == TruckStatus.IN_USE

    def test_assign_truck_to_delivery_updates_assigned_truck_status_in_repository(self):
        truck = Truck(
            id="truck-available",
            plate_number="AA-111-AA",
            capacity_kg=1000,
            status=TruckStatus.AVAILABLE,
        )

        truck_repository.save_truck(truck)

        request = TruckAssignmentRequest(
            delivery_id="delivery-123",
            cargo_weight_kg=700,
        )

        assigned_truck = assignment_service.assign_truck_to_delivery(request)

        trucks = truck_repository.get_trucks()

        assert assigned_truck.status == TruckStatus.IN_USE
        assert len(trucks) == 1
        assert trucks[0].id == "truck-available"
        assert trucks[0].status == TruckStatus.IN_USE

    def test_assign_truck_to_delivery_does_not_assign_truck_with_insufficient_capacity(self):
        truck = Truck(
            id="truck-small",
            plate_number="AA-111-AA",
            capacity_kg=500,
            status=TruckStatus.AVAILABLE,
        )

        truck_repository.save_truck(truck)

        request = TruckAssignmentRequest(
            delivery_id="delivery-123",
            cargo_weight_kg=700,
        )

        with pytest.raises(NoTruckAvailable):
            assignment_service.assign_truck_to_delivery(request)

    def test_assign_truck_to_delivery_does_not_assign_truck_in_use(self):
        truck = Truck(
            id="truck-in-use",
            plate_number="AA-111-AA",
            capacity_kg=1000,
            status=TruckStatus.IN_USE,
        )

        truck_repository.save_truck(truck)

        request = TruckAssignmentRequest(
            delivery_id="delivery-123",
            cargo_weight_kg=700,
        )

        with pytest.raises(NoTruckAvailable):
            assignment_service.assign_truck_to_delivery(request)

    def test_assign_truck_to_delivery_does_not_assign_truck_in_repair(self):
        truck = Truck(
            id="truck-in-repair",
            plate_number="AA-111-AA",
            capacity_kg=1000,
            status=TruckStatus.IN_REPAIR,
        )

        truck_repository.save_truck(truck)

        request = TruckAssignmentRequest(
            delivery_id="delivery-123",
            cargo_weight_kg=700,
        )

        with pytest.raises(NoTruckAvailable):
            assignment_service.assign_truck_to_delivery(request)

    def test_assign_truck_to_delivery_rejects_invalid_cargo_weight(self):
        request = TruckAssignmentRequest(
            delivery_id="delivery-123",
            cargo_weight_kg=0,
        )

        with pytest.raises(InvalidCargoWeight):
            assignment_service.assign_truck_to_delivery(request)