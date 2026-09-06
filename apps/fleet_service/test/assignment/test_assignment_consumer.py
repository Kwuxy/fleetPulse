import asyncio
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.clients.kafka_client import QueueMessageStatus
from app.consumers import assignment_consumer
from app.producers import assignment_producer
from app.exceptions import InvalidCargoWeight, NoTruckAvailable, UnknownDelivery
from app.models.assignment import TruckAssignmentCompleted, TruckAssignmentFailureReason, TruckAssignmentRequest
from app.models.truck import Truck, TruckStatus


@pytest.mark.kafka
@pytest.mark.unit
class TestAssignmentConsumer:
    class TestBuildTruckAssignmentRequest:
        def test_building_assignment_request_success_on_valid_message(self):
            # - Arrange -
            msg = {"delivery_id": "delivery-abc123", "cargo_weight_kg": 700}

            # - Act -
            result = assignment_consumer._build_truck_assignment_request(msg)

            # - Assert Result -
            assert result == TruckAssignmentRequest(delivery_id="delivery-abc123", cargo_weight_kg=700)

        def test_building_assignment_request_rejects_on_incomplete_message(self):
            # - Arrange -
            msg = {"delivery_id": "delivery-abc123"}  # missing required `cargo_weight_kg`

            # - Act & Assert -
            with pytest.raises(ValidationError):
                assignment_consumer._build_truck_assignment_request(msg)

            # - Assert Result -
            # Exception raised, no assertions needed

    class TestHandleTruckAssignmentRequested:
        def test_assigns_truck_and_produces_success_completion_on_valid_message(self, monkeypatch):
            # - Arrange -
            truck = Truck(id="truck-123", plate_number="AA-111-AA", capacity_kg=1000, status=TruckStatus.IN_USE)
            mock_assign_truck_to_delivery = AsyncMock(return_value=truck)
            monkeypatch.setattr(assignment_consumer.assignment_service, "assign_truck_to_delivery",
                                mock_assign_truck_to_delivery)
            mock_produce = AsyncMock()
            monkeypatch.setattr(assignment_producer, "produce_truck_assignment_completed", mock_produce)

            msg = {"delivery_id": "delivery-abc123", "cargo_weight_kg": 700}

            # - Act -
            result = asyncio.run(assignment_consumer.handle_truck_assignment_requested(msg))

            # - Assert Result -
            assert result == QueueMessageStatus.CONSUMED

            # - Assert mock calls -
            mock_produce.assert_awaited_once_with(
                TruckAssignmentCompleted.get_success(delivery_id="delivery-abc123", truck_id="truck-123")
            )

        @staticmethod
        def raise_unknown_delivery(request):
            raise UnknownDelivery(request.delivery_id)

        @staticmethod
        def raise_invalid_cargo(request):
            raise InvalidCargoWeight(request.cargo_weight_kg)

        @staticmethod
        def raise_no_truck(request):
            raise NoTruckAvailable(request.cargo_weight_kg)

        @pytest.mark.parametrize("side_effect_exception, expected_reason", [
            (raise_unknown_delivery, TruckAssignmentFailureReason.INVALID_REQUEST),
            (raise_invalid_cargo, TruckAssignmentFailureReason.INVALID_REQUEST),
            (raise_no_truck, TruckAssignmentFailureReason.NO_AVAILABLE_TRUCK),
        ])
        def test_produces_invalid_request_completion_on_assignment_error(self, monkeypatch, side_effect_exception,
                                                                         expected_reason):
            # - Arrange -
            mock_assign_truck_to_delivery = AsyncMock(side_effect=side_effect_exception)
            monkeypatch.setattr(assignment_consumer.assignment_service, "assign_truck_to_delivery",
                                mock_assign_truck_to_delivery)
            mock_produce = AsyncMock()
            monkeypatch.setattr(assignment_producer, "produce_truck_assignment_completed", mock_produce)

            msg = {"delivery_id": "delivery-abc123", "cargo_weight_kg": 700}

            # - Act -
            result = asyncio.run(assignment_consumer.handle_truck_assignment_requested(msg))

            # - Assert Result -
            assert result == QueueMessageStatus.CONSUMED

            # - Assert mock calls -
            mock_produce.assert_awaited_once()
            completed = mock_produce.await_args.args[0]
            assert completed.delivery_id == "delivery-abc123"
            assert completed.truck_id is None
            assert completed.assigned is False
            assert completed.reason == expected_reason
            assert completed.description is not None
            assert completed.description != ''

        def test_returns_consumed_without_assigning_on_malformed_message(self, monkeypatch):
            # - Arrange -
            mock_assign_truck_to_delivery = AsyncMock()
            monkeypatch.setattr(assignment_consumer.assignment_service, "assign_truck_to_delivery",
                                mock_assign_truck_to_delivery)
            mock_produce = AsyncMock()
            monkeypatch.setattr(assignment_producer, "produce_truck_assignment_completed", mock_produce)

            msg = {"delivery_id": "delivery-abc123"}  # missing required `cargo_weight_kg`

            # - Act -
            result = asyncio.run(assignment_consumer.handle_truck_assignment_requested(msg))

            # - Assert Result -
            assert result == QueueMessageStatus.CONSUMED

            # - Assert mock calls -
            mock_assign_truck_to_delivery.assert_not_awaited()
            mock_produce.assert_not_awaited()
