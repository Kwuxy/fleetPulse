import asyncio
from unittest.mock import AsyncMock

import pytest

from app.exceptions import InvalidCargoWeight, NoTruckAvailable
from app.models.assignment import TruckAssignmentRequest
from app.models.truck import Truck, TruckStatus
from app.repositories import truck_repository, assignment_repository
from app.services import assignment_service


@pytest.mark.service
@pytest.mark.unit
class TestAssignmentService:
    @pytest.fixture(autouse=True)
    def mock_save_truck(self, monkeypatch):
        mock = AsyncMock()
        monkeypatch.setattr(truck_repository, "save_truck", mock)
        return mock

    def test_assign_truck_to_delivery_succeeds_and_marks_truck_in_use(self, monkeypatch, mock_save_truck):
        # - Arrange -
        expected_truck = self._get_truck()
        mock_find_available_truck_for_capacity = AsyncMock(return_value=expected_truck)
        monkeypatch.setattr(assignment_repository, "find_available_truck_for_capacity",
                            mock_find_available_truck_for_capacity)

        request = TruckAssignmentRequest(
            delivery_id="delivery-abc123",
            cargo_weight_kg=700
        )

        # - Act -
        truck = asyncio.run(assignment_service.assign_truck_to_delivery(request))

        # - Assert Result -
        assert truck.id == expected_truck.id
        assert truck.plate_number == expected_truck.plate_number
        assert truck.capacity_kg == expected_truck.capacity_kg
        assert truck.status == TruckStatus.IN_USE

        # - Assert mock calls -
        mock_save_truck.assert_awaited_once_with(truck)
        mock_find_available_truck_for_capacity.assert_awaited_once_with(request.cargo_weight_kg)

    def test_assign_truck_to_delivery_rejects_invalid_cargo_weight(self, monkeypatch, mock_save_truck):
        # - Arrange -
        expected_truck = self._get_truck()
        mock_find_available_truck_for_capacity = AsyncMock(return_value=expected_truck)
        monkeypatch.setattr(assignment_repository, "find_available_truck_for_capacity",
                            mock_find_available_truck_for_capacity)

        request = TruckAssignmentRequest(
            delivery_id="delivery-abc123",
            cargo_weight_kg=0
        )

        # - Act -
        with pytest.raises(InvalidCargoWeight):
            asyncio.run(assignment_service.assign_truck_to_delivery(request))

        # - Assert Result -
        # Exception raised, no assertions needed

        # - Assert mock calls -
        mock_save_truck.assert_not_awaited()
        mock_find_available_truck_for_capacity.assert_not_awaited()

    def test_assign_truck_to_delivery_raises_no_truck_available(self, monkeypatch, mock_save_truck):
        # - Arrange -
        mock_find_available_truck_for_capacity = AsyncMock(return_value=None)
        monkeypatch.setattr(assignment_repository, "find_available_truck_for_capacity",
                            mock_find_available_truck_for_capacity)

        request = TruckAssignmentRequest(
            delivery_id="delivery-abc123",
            cargo_weight_kg=700
        )

        # - Act -
        with pytest.raises(NoTruckAvailable):
            asyncio.run(assignment_service.assign_truck_to_delivery(request))

        # - Assert Result -
        # Exception raised, no assertions needed

        # - Assert mock calls -
        mock_save_truck.assert_not_awaited()
        mock_find_available_truck_for_capacity.assert_awaited_once_with(request.cargo_weight_kg)

    @staticmethod
    def _get_truck(**overrides):
        defaults = dict(
            id="truck-123",
            plate_number="AB-123-CD",
            capacity_kg=1200,
            status=TruckStatus.AVAILABLE
        )
        defaults.update(overrides)
        return Truck(**defaults)
