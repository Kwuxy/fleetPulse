import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient

from apps.delivery_service.app.main import app
from apps.delivery_service.app.repositories import delivery_repository
from apps.delivery_service.app.services import delivery_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_repository():
    delivery_repository.clear()


@pytest.mark.routes
@pytest.mark.integration
class TestDeliveryRoutes:
    def test_create_delivery_endpoint_returns_created_delivery_when_truck_is_assigned(self, monkeypatch):
        async def fake_assign_truck_to_delivery(delivery_id: str, cargo_weight_kg: int) -> str:
            return "truck-123"

        monkeypatch.setattr(
            delivery_service.fleet_client,
            "assign_truck_to_delivery",
            fake_assign_truck_to_delivery,
        )

        response = client.post(
            "/deliveries",
            json={
                "client_id": 1,
                "pickup_location": "Brussels",
                "dropoff_location": "Paris",
                "cargo_weight_kg": 700,
                "requested_date": str(date.today() + timedelta(days=1)),
            },
        )

        assert response.status_code == 201

        body = response.json()

        assert body["id"].startswith("delivery-")
        assert body["client_id"] == 1
        assert body["pickup_location"] == "Brussels"
        assert body["dropoff_location"] == "Paris"
        assert body["cargo_weight_kg"] == 700
        assert body["status"] == "assigned"
        assert body["assigned_truck_id"] == "truck-123"

    def test_create_delivery_endpoint_returns_denied_delivery_when_no_truck_is_available(self, monkeypatch):
        async def fake_assign_truck_to_delivery(delivery_id: str, cargo_weight_kg: int) -> None:
            return None

        monkeypatch.setattr(
            delivery_service.fleet_client,
            "assign_truck_to_delivery",
            fake_assign_truck_to_delivery,
        )

        response = client.post(
            "/deliveries",
            json={
                "client_id": 1,
                "pickup_location": "Brussels",
                "dropoff_location": "Paris",
                "cargo_weight_kg": 700,
                "requested_date": str(date.today() + timedelta(days=1)),
            },
        )

        assert response.status_code == 201

        body = response.json()

        assert body["id"].startswith("delivery-")
        assert body["status"] == "denied"
        assert body["assigned_truck_id"] is None

    def test_create_delivery_endpoint_rejects_same_pickup_and_dropoff_locations(self, monkeypatch):
        async def fake_assign_truck_to_delivery(delivery_id: str, cargo_weight_kg: int) -> str:
            return "truck-123"

        monkeypatch.setattr(
            delivery_service.fleet_client,
            "assign_truck_to_delivery",
            fake_assign_truck_to_delivery,
        )

        response = client.post(
            "/deliveries",
            json={
                "client_id": 1,
                "pickup_location": "Brussels",
                "dropoff_location": "Brussels",
                "cargo_weight_kg": 700,
                "requested_date": str(date.today() + timedelta(days=1)),
            },
        )

        assert response.status_code == 400

    def test_create_delivery_endpoint_rejects_invalid_cargo_weight(self, monkeypatch):
        async def fake_assign_truck_to_delivery(delivery_id: str, cargo_weight_kg: int) -> str:
            return "truck-123"

        monkeypatch.setattr(
            delivery_service.fleet_client,
            "assign_truck_to_delivery",
            fake_assign_truck_to_delivery,
        )

        response = client.post(
            "/deliveries",
            json={
                "client_id": 1,
                "pickup_location": "Brussels",
                "dropoff_location": "Paris",
                "cargo_weight_kg": 0,
                "requested_date": str(date.today() + timedelta(days=1)),
            },
        )

        assert response.status_code == 400

    def test_create_delivery_endpoint_rejects_invalid_requested_date(self, monkeypatch):
        async def fake_assign_truck_to_delivery(delivery_id: str, cargo_weight_kg: int) -> str:
            return "truck-123"

        monkeypatch.setattr(
            delivery_service.fleet_client,
            "assign_truck_to_delivery",
            fake_assign_truck_to_delivery,
        )

        response = client.post(
            "/deliveries",
            json={
                "client_id": 1,
                "pickup_location": "Brussels",
                "dropoff_location": "Paris",
                "cargo_weight_kg": 700,
                "requested_date": str(date.today()),
            },
        )

        assert response.status_code == 400
