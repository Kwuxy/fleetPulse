import asyncio
from unittest.mock import AsyncMock

import pytest

from app.models.truck_assignment import TruckAssignmentRequest
from app.producers import assignment_producer


@pytest.mark.kafka
@pytest.mark.unit
class TestProduceTruckAssignmentRequested:
    def test_sends_request_to_truck_assignment_requested_topic(self, monkeypatch):
        mock_producer = AsyncMock()
        monkeypatch.setattr(assignment_producer, "get_producer", lambda: mock_producer)

        request = TruckAssignmentRequest(delivery_id="delivery-abc123", cargo_weight_kg=700)
        asyncio.run(assignment_producer.produce_truck_assignment_requested(request))

        mock_producer.send.assert_awaited_once_with(
            "truck-assignment-requested",
            key="delivery-abc123",
            value=request.model_dump(),
        )
