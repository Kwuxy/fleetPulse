import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import delivery_repository

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_repository():
    delivery_repository.clear()


@pytest.mark.routes
@pytest.mark.integration
class TestDeliveryRoutes:
    def test_create_delivery_endpoint_returns_created_delivery_when_truck_is_assigned(self):
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

    def test_create_delivery_endpoint_returns_denied_delivery_when_no_truck_is_available(self):
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

    def test_create_delivery_endpoint_rejects_same_pickup_and_dropoff_locations(self):
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

    def test_create_delivery_endpoint_rejects_invalid_cargo_weight(self):
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

    def test_create_delivery_endpoint_rejects_invalid_requested_date(self):
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

    def test_get_deliveries_endpoint_returns_created_deliveries(self):
        client.post(
            "/deliveries",
            json={
                "client_id": 1,
                "pickup_location": "Brussels",
                "dropoff_location": "Paris",
                "cargo_weight_kg": 700,
                "requested_date": str(date.today() + timedelta(days=1)),
            },
        )

        client.post(
            "/deliveries",
            json={
                "client_id": 2,
                "pickup_location": "Rome",
                "dropoff_location": "Berlin",
                "cargo_weight_kg": 900,
                "requested_date": str(date.today() + timedelta(days=1)),
            },
        )

        response = client.get("/deliveries")

        assert response.status_code == 200
        assert len(response.json()) == 2
        assert response.json()[0]["pickup_location"] == "Brussels"
        assert response.json()[1]["pickup_location"] == "Rome"

    def test_get_delivery_by_id_endpoint_returns_created_deliveries(self):
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

        client.post(
            "/deliveries",
            json={
                "client_id": 2,
                "pickup_location": "Rome",
                "dropoff_location": "Berlin",
                "cargo_weight_kg": 900,
                "requested_date": str(date.today() + timedelta(days=1)),
            },
        )

        delivery_id = response.json()["id"]
        response = client.get(f"/deliveries/{delivery_id}")

        assert response.status_code == 200
        assert response.json()["pickup_location"] == "Brussels"

    def test_get_delivery_by_id_endpoint_returns_404(self):
        client.post(
            "/deliveries",
            json={
                "client_id": 1,
                "pickup_location": "Brussels",
                "dropoff_location": "Paris",
                "cargo_weight_kg": 700,
                "requested_date": str(date.today() + timedelta(days=1)),
            },
        )

        response = client.get(f"/delivery/fake_id")
        assert response.status_code == 404
