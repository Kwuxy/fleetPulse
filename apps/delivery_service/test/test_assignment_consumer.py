import asyncio

import pytest

from app.clients.kafka_client import QueueMessageStatus
from app.consumers import assignment_consumer
from app.exceptions import NotFoundException
from app.models.truck_assignment import TruckAssignmentCompleted


@pytest.mark.kafka
@pytest.mark.unit
class TestHandleTruckAssignmentCompleted:
    def test_updates_delivery_and_returns_consumed_on_valid_message(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            assignment_consumer.delivery_service,
            "update_delivery_with_truck_assignment",
            lambda assignment: calls.append(assignment),
        )

        msg = {"delivery_id": "delivery-abc123", "truck_id": "truck-123", "assigned": True}
        result = asyncio.run(assignment_consumer.handle_truck_assignment_completed(msg))

        assert result == QueueMessageStatus.CONSUMED
        assert calls == [TruckAssignmentCompleted(**msg)]

    def test_returns_consumed_without_raising_on_unknown_delivery(self, monkeypatch):
        def raise_not_found(assignment):
            raise NotFoundException(assignment.delivery_id)

        monkeypatch.setattr(
            assignment_consumer.delivery_service, "update_delivery_with_truck_assignment", raise_not_found
        )

        msg = {"delivery_id": "fake_id", "assigned": False}
        result = asyncio.run(assignment_consumer.handle_truck_assignment_completed(msg))

        assert result == QueueMessageStatus.CONSUMED

    def test_returns_consumed_without_updating_on_malformed_message(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            assignment_consumer.delivery_service,
            "update_delivery_with_truck_assignment",
            lambda assignment: calls.append(assignment),
        )

        msg = {"delivery_id": "delivery-abc123"}  # missing required `assigned` field

        result = asyncio.run(assignment_consumer.handle_truck_assignment_completed(msg))

        assert result == QueueMessageStatus.CONSUMED
        assert calls == []
