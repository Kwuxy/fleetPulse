from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.truck import Truck, TruckStatus, CreateTruckRequest
from app.services import truck_service
from app.exceptions import InvalidTruckCapacity, InvalidPlateNumber, DuplicatePlateNumber

client = TestClient(app)


@pytest.mark.routes
@pytest.mark.unit
class TestTruckRoutes:
    class TestCreateTruckEndpoint:
        def test_create_truck_endpoint_returns_created_truck(self, monkeypatch):
            # - Arrange -
            truck = Truck(id="truck-1", plate_number="AB-123-CD", capacity_kg=1200, status=TruckStatus.AVAILABLE)
            mock_create_truck = AsyncMock(return_value=truck)
            monkeypatch.setattr(truck_service, "create_truck", mock_create_truck)

            request = CreateTruckRequest(plate_number="AB-123-CD", capacity_kg=1200)

            # - Act -
            response = client.post("/trucks", json={"plate_number": "AB-123-CD", "capacity_kg": 1200})

            # - Assert result -
            assert response.status_code == 201
            assert response.json() == truck.model_dump(mode="json")

            # - Assert mock -
            mock_create_truck.assert_awaited_once_with(request)

        @staticmethod
        def raise_invalid_capacity(req: CreateTruckRequest):
            raise InvalidTruckCapacity(req.capacity_kg)

        @staticmethod
        def raise_invalid_plate_number(req: CreateTruckRequest):
            raise InvalidPlateNumber(req.plate_number)

        @staticmethod
        def raise_duplicate_plate_number(req: CreateTruckRequest):
            raise DuplicatePlateNumber(req.plate_number)

        @pytest.mark.parametrize('side_effect_exception, payload, expected_response_code', [
            (raise_invalid_capacity, {"plate_number": "AB-123-CD", "capacity_kg": 0}, 400),
            (raise_invalid_plate_number, {"plate_number": "AB-123-CD", "capacity_kg": 1200}, 400),
            (raise_duplicate_plate_number, {"plate_number": "AB-123-CD", "capacity_kg": 1200}, 409),
        ])
        def test_create_truck_endpoint_rejects_exceptions(self, monkeypatch, side_effect_exception, payload,
                                                          expected_response_code):
            # - Arrange -
            mock_create_truck = AsyncMock(side_effect=side_effect_exception)
            monkeypatch.setattr(truck_service, "create_truck", mock_create_truck)

            request = CreateTruckRequest(**payload)

            # - Act -
            response = client.post("/trucks", json=payload)

            # - Assert result -
            assert response.status_code == expected_response_code

            # - Assert mock -
            mock_create_truck.assert_awaited_once_with(request)

    class TestGetTrucksEndpoint:
        def test_get_trucks_endpoint_returns_empty_list_when_no_trucks_exist(self, monkeypatch):
            # - Arrange -
            mock_get_trucks = AsyncMock(return_value=[])
            monkeypatch.setattr(truck_service, "get_trucks", mock_get_trucks)

            # - Act -
            response = client.get("/trucks")

            # - Assert result -
            assert response.status_code == 200
            assert response.json() == []

            # - Assert mock -
            mock_get_trucks.assert_awaited_once()

        def test_get_trucks_endpoint_returns_trucks_from_service(self, monkeypatch):
            # - Arrange -
            trucks = [
                Truck(id="truck-1234", plate_number="AB-123-CD", capacity_kg=1200, status=TruckStatus.AVAILABLE),
                Truck(id="truck-4567", plate_number="ZZ-987-GF", capacity_kg=500, status=TruckStatus.IN_USE),
            ]
            mock_get_trucks = AsyncMock(return_value=trucks)
            monkeypatch.setattr(truck_service, "get_trucks", mock_get_trucks)

            # - Act -
            response = client.get("/trucks")

            # - Assert result -
            assert response.status_code == 200
            assert response.json() == [truck.model_dump(mode="json") for truck in trucks]

            # - Assert mock -
            mock_get_trucks.assert_awaited_once()
