import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.main import app
from app.producers import assignment_producer
from app.repositories import delivery_repository

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_repository():
    delivery_repository.clear()


@pytest.fixture(autouse=True)
def mock_produce_truck_assignment_requested(monkeypatch):
    monkeypatch.setattr(assignment_producer, "produce_truck_assignment_requested", AsyncMock())


def _valid_payload(**overrides):
    defaults = {
        "client_id": 1,
        "pickup_location": "Brussels",
        "dropoff_location": "Paris",
        "cargo_weight_kg": 700,
        "requested_date": str(date.today() + timedelta(days=1)),
    }
    defaults.update(overrides)
    return defaults


@pytest.mark.routes
@pytest.mark.integration
class TestDeliveryRoutes:
    def test_create_delivery_endpoint_returns_requested_delivery(self):
        response = client.post("/deliveries", json=_valid_payload())

        assert response.status_code == 201

        body = response.json()

        assert body["id"].startswith("delivery-")
        assert body["client_id"] == 1
        assert body["pickup_location"] == "Brussels"
        assert body["dropoff_location"] == "Paris"
        assert body["cargo_weight_kg"] == 700
        assert body["status"] == "requested"
        assert body["assigned_truck_id"] is None

    def test_create_delivery_endpoint_rejects_same_pickup_and_dropoff_locations(self):
        response = client.post("/deliveries", json=_valid_payload(dropoff_location="Brussels"))
        assert response.status_code == 400

    def test_create_delivery_endpoint_rejects_invalid_cargo_weight(self):
        response = client.post("/deliveries", json=_valid_payload(cargo_weight_kg=0))
        assert response.status_code == 400

    def test_create_delivery_endpoint_rejects_invalid_requested_date(self):
        response = client.post("/deliveries", json=_valid_payload(requested_date=str(date.today())))
        assert response.status_code == 400

    def test_get_deliveries_endpoint_returns_created_deliveries(self):
        client.post("/deliveries", json=_valid_payload())
        client.post(
            "/deliveries",
            json=_valid_payload(client_id=2, pickup_location="Rome", dropoff_location="Berlin", cargo_weight_kg=900),
        )

        response = client.get("/deliveries")

        assert response.status_code == 200
        assert len(response.json()) == 2
        assert response.json()[0]["pickup_location"] == "Brussels"
        assert response.json()[1]["pickup_location"] == "Rome"

    def test_get_delivery_by_id_endpoint_returns_created_deliveries(self):
        response = client.post("/deliveries", json=_valid_payload())
        client.post(
            "/deliveries",
            json=_valid_payload(client_id=2, pickup_location="Rome", dropoff_location="Berlin", cargo_weight_kg=900),
        )

        delivery_id = response.json()["id"]
        response = client.get(f"/deliveries/{delivery_id}")

        assert response.status_code == 200
        assert response.json()["pickup_location"] == "Brussels"

    def test_get_delivery_by_id_endpoint_returns_404(self):
        client.post("/deliveries", json=_valid_payload())

        response = client.get("/deliveries/fake_id")
        assert response.status_code == 404
