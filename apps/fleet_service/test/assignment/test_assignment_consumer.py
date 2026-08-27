import asyncio
from unittest.mock import AsyncMock

import pytest

from app.clients.kafka_client import QueueMessageStatus
from app.consumers import assignment_consumer
from app.exceptions import InvalidCargoWeight, NoTruckAvailable, UnknownDelivery
from app.models.assignment import TruckAssignmentCompleted, TruckAssignmentFailureReason
from app.models.truck import Truck, TruckStatus


@pytest.mark.kafka
@pytest.mark.unit
class TestHandleTruckAssignmentRequested:
    def test_assigns_truck_and_produces_success_completion_on_valid_message(self, monkeypatch):
        truck = Truck(id="truck-123", plate_number="AA-111-AA", capacity_kg=1000, status=TruckStatus.IN_USE)
        monkeypatch.setattr(assignment_consumer.assignment_service, "assign_truck_to_delivery", lambda request: truck)
        mock_produce = AsyncMock()
        monkeypatch.setattr(assignment_consumer, "produce_truck_assignment_completed", mock_produce)

        msg = {"delivery_id": "delivery-abc123", "cargo_weight_kg": 700}
        result = asyncio.run(assignment_consumer.handle_truck_assignment_requested(msg))

        assert result == QueueMessageStatus.CONSUMED
        mock_produce.assert_awaited_once_with(
            TruckAssignmentCompleted.get_success(delivery_id="delivery-abc123", truck_id="truck-123")
        )

    def test_produces_invalid_request_completion_on_unknown_delivery(self, monkeypatch):
        def raise_unknown_delivery(request):
            raise UnknownDelivery(request.delivery_id)

        monkeypatch.setattr(assignment_consumer.assignment_service, "assign_truck_to_delivery", raise_unknown_delivery)
        mock_produce = AsyncMock()
        monkeypatch.setattr(assignment_consumer, "produce_truck_assignment_completed", mock_produce)

        msg = {"delivery_id": "delivery-abc123", "cargo_weight_kg": 700}
        result = asyncio.run(assignment_consumer.handle_truck_assignment_requested(msg))

        assert result == QueueMessageStatus.CONSUMED
        completed = mock_produce.await_args.args[0]
        assert completed.assigned is False
        assert completed.reason == TruckAssignmentFailureReason.INVALID_REQUEST

    def test_produces_invalid_request_completion_on_invalid_cargo_weight(self, monkeypatch):
        def raise_invalid_cargo(request):
            raise InvalidCargoWeight(request.cargo_weight_kg)

        monkeypatch.setattr(assignment_consumer.assignment_service, "assign_truck_to_delivery", raise_invalid_cargo)
        mock_produce = AsyncMock()
        monkeypatch.setattr(assignment_consumer, "produce_truck_assignment_completed", mock_produce)

        msg = {"delivery_id": "delivery-abc123", "cargo_weight_kg": 0}
        result = asyncio.run(assignment_consumer.handle_truck_assignment_requested(msg))

        assert result == QueueMessageStatus.CONSUMED
        completed = mock_produce.await_args.args[0]
        assert completed.assigned is False
        assert completed.reason == TruckAssignmentFailureReason.INVALID_REQUEST

    def test_produces_no_available_truck_completion_when_no_truck_available(self, monkeypatch):
        def raise_no_truck(request):
            raise NoTruckAvailable(request.cargo_weight_kg)

        monkeypatch.setattr(assignment_consumer.assignment_service, "assign_truck_to_delivery", raise_no_truck)
        mock_produce = AsyncMock()
        monkeypatch.setattr(assignment_consumer, "produce_truck_assignment_completed", mock_produce)

        msg = {"delivery_id": "delivery-abc123", "cargo_weight_kg": 700}
        result = asyncio.run(assignment_consumer.handle_truck_assignment_requested(msg))

        assert result == QueueMessageStatus.CONSUMED
        completed = mock_produce.await_args.args[0]
        assert completed.assigned is False
        assert completed.reason == TruckAssignmentFailureReason.NO_AVAILABLE_TRUCK

    def test_returns_consumed_without_assigning_on_malformed_message(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            assignment_consumer.assignment_service,
            "assign_truck_to_delivery",
            lambda request: calls.append(request),
        )
        mock_produce = AsyncMock()
        monkeypatch.setattr(assignment_consumer, "produce_truck_assignment_completed", mock_produce)

        msg = {"delivery_id": "delivery-abc123"}  # missing required `cargo_weight_kg`
        result = asyncio.run(assignment_consumer.handle_truck_assignment_requested(msg))

        assert result == QueueMessageStatus.CONSUMED
        assert calls == []
        mock_produce.assert_not_awaited()
