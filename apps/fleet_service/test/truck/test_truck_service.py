import asyncio
from unittest.mock import AsyncMock

import pytest

from app.exceptions import InvalidTruckCapacity, DuplicatePlateNumber
from app.models.truck import CreateTruckRequest, TruckStatus, Truck
from app.repositories import truck_repository
from app.services import truck_service


@pytest.mark.service
@pytest.mark.unit
class TestTruckService:
    class TestCreateTruck:
        @pytest.fixture(autouse=True)
        def mock_save_truck(self, monkeypatch):
            mock = AsyncMock()
            monkeypatch.setattr(truck_repository, "save_truck", mock)
            return mock

        def test_create_truck_succeeds_on_valid_data(self, monkeypatch, mock_save_truck):
            # - Arrange -
            mock_get_by_plate = AsyncMock(return_value=None)
            monkeypatch.setattr(truck_repository, "get_truck_by_plate_number", mock_get_by_plate)

            request = CreateTruckRequest(
                plate_number="AB-123-CD",
                capacity_kg=1200,
            )

            # - Act -
            truck = asyncio.run(truck_service.create_truck(request))

            # - Assert Result -
            assert truck.id.startswith("truck-")
            assert truck.plate_number == "AB-123-CD"
            assert truck.capacity_kg == 1200
            assert truck.status == TruckStatus.AVAILABLE

            # - Assert mock calls -
            mock_save_truck.assert_awaited_once_with(truck)

        def test_create_truck_rejects_invalid_capacity(self, monkeypatch, mock_save_truck):
            # - Arrange -
            mock_get_by_plate = AsyncMock(return_value=None)
            monkeypatch.setattr(truck_repository, "get_truck_by_plate_number", mock_get_by_plate)

            request = CreateTruckRequest(
                plate_number="AB-123-CD",
                capacity_kg=0,
            )

            # - Act -
            with pytest.raises(InvalidTruckCapacity):
                asyncio.run(truck_service.create_truck(request))

            # - Assert mock calls -
            mock_save_truck.assert_not_awaited()

        def test_create_truck_rejects_duplicate_plate_number(self, monkeypatch, mock_save_truck):
            # - Arrange -
            already_registered_truck = Truck(
                id="truck-1",
                plate_number="AB-123-CD",
                capacity_kg=1200,
                status=TruckStatus.AVAILABLE,
            )

            mock_get_by_plate = AsyncMock(return_value=already_registered_truck)
            monkeypatch.setattr(truck_repository, "get_truck_by_plate_number", mock_get_by_plate)

            request = CreateTruckRequest(
                plate_number="AB-123-CD",
                capacity_kg=854,
            )

            # - Act -
            with pytest.raises(DuplicatePlateNumber):
                asyncio.run(truck_service.create_truck(request))

            # - Assert mock calls -
            mock_save_truck.assert_not_awaited()

    class TestGetTrucks:
        def test_get_truck_returns_created_trucks(self, monkeypatch):
            # - Arrange -
            initial_trucks = [
                Truck(
                    id="truck-1",
                    plate_number="AB-123-CD",
                    capacity_kg=1200,
                    status=TruckStatus.AVAILABLE,
                ),
                Truck(
                    id="truck-2",
                    plate_number="AB-456-EF",
                    capacity_kg=1000,
                    status=TruckStatus.IN_USE,
                )
            ]

            mock_get_trucks = AsyncMock(return_value=initial_trucks)
            monkeypatch.setattr(truck_repository, "get_trucks", mock_get_trucks)

            # - Act -
            trucks = asyncio.run(truck_service.get_trucks())

            # - Assert Result -
            assert trucks == initial_trucks

            # - Assert mock calls -
            mock_get_trucks.assert_awaited_once()
