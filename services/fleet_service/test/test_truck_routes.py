import pytest
from fastapi.testclient import TestClient

from services.fleet_service.app.main import app
from services.fleet_service.app.repositories import truck_repository

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_repository():
    truck_repository.clear()

def test_create_truck_endpoint():
    response = client.post(
        "/trucks",
        json={
            "plate_number": "AB-123-CD",
            "capacity_kg": 1200,
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["id"].startswith("truck-")
    assert body["plate_number"] == "AB-123-CD"
    assert body["capacity_kg"] == 1200
    assert body["status"] == "available"


def test_get_trucks_endpoint_returns_created_trucks():
    client.post(
        "/trucks",
        json={
            "plate_number": "AB-123-CD",
            "capacity_kg": 1200,
        },
    )

    response = client.get("/trucks")

    assert response.status_code == 200

    body = response.json()

    assert len(body) == 1
    assert body[0]["plate_number"] == "AB-123-CD"
    assert body[0]["capacity_kg"] == 1200


def test_create_truck_endpoint_rejects_invalid_capacity():
    response = client.post(
        "/trucks",
        json={
            "plate_number": "AB-123-CD",
            "capacity_kg": 0,
        },
    )

    assert response.status_code == 400

def test_create_truck_endpoint_rejects_duplicate_plate_number():
    client.post(
        "/trucks",
        json={
            "plate_number": "AB-123-CD",
            "capacity_kg": 900,
        },
    )

    response = client.post(
        "/trucks",
        json={
            "plate_number": "AB-123-CD",
            "capacity_kg": 1100,
        },
    )

    assert response.status_code == 409
