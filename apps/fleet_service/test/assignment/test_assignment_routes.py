import pytest
from fastapi.testclient import TestClient

from main import app
from models.truck import Truck, TruckStatus
from repositories import truck_repository

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_repository():
    truck_repository.clear()


@pytest.mark.routes
@pytest.mark.integration
class TestAssignmentRoutes:
    def test_assign_truck_endpoint_assigns_available_truck(self):
        truck = Truck(
            id="truck-available",
            plate_number="AA-111-AA",
            capacity_kg=1000,
            status=TruckStatus.AVAILABLE,
        )

        truck_repository.save_truck(truck)

        response = client.post(
            "/internal/truck-assignments",
            json={
                "delivery_id": "delivery-123",
                "cargo_weight_kg": 700,
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["assigned"] is True
        assert body["truck_id"] == "truck-available"
        assert body["reason"] is None

    def test_assign_truck_endpoint_assigns_smallest_sufficient_available_truck(self):
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

        response = client.post(
            "/internal/truck-assignments",
            json={
                "delivery_id": "delivery-123",
                "cargo_weight_kg": 700,
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["assigned"] is True
        assert body["truck_id"] == "truck-small"
        assert body["reason"] is None

    def test_assign_truck_endpoint_returns_not_assigned_when_no_truck_available(self):
        truck = Truck(
            id="truck-in-use",
            plate_number="AA-111-AA",
            capacity_kg=1000,
            status=TruckStatus.IN_USE,
        )

        truck_repository.save_truck(truck)

        response = client.post(
            "/internal/truck-assignments",
            json={
                "delivery_id": "delivery-123",
                "cargo_weight_kg": 700,
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["assigned"] is False
        assert body["truck_id"] is None
        assert body["reason"] == "NO_AVAILABLE_TRUCK"

    def test_assign_truck_endpoint_rejects_invalid_cargo_weight(self):
        response = client.post(
            "/internal/truck-assignments",
            json={
                "delivery_id": "delivery-123",
                "cargo_weight_kg": 0,
            },
        )

        assert response.status_code == 400