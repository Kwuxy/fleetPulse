import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.assignment import TruckAssignmentCompleted
from app.producers import assignment_producer


@pytest.mark.kafka
@pytest.mark.unit
class TestProduceTruckAssignmentCompleted:
    def test_sends_completed_assignment_to_truck_assignment_completed_topic(self, monkeypatch):
        mock_producer = AsyncMock()
        mock_producer.send.return_value = MagicMock()
        monkeypatch.setattr(assignment_producer, "get_producer", lambda: mock_producer)

        completed = TruckAssignmentCompleted.get_success(delivery_id="delivery-abc123", truck_id="truck-123")
        asyncio.run(assignment_producer.produce_truck_assignment_completed(completed))

        mock_producer.send.assert_awaited_once_with(
            "truck-assignment-completed",
            key="delivery-abc123",
            value=completed.model_dump(),
        )
