import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.truck_assignment import TruckAssignmentRequest
from app.producers import assignment_producer
from app.clients import kafka_client


@pytest.mark.kafka
@pytest.mark.unit
class TestTruckAssignmentRequestedProducer:
    class TestProduceTruckAssignmentRequested:
        def test_sends_request_to_truck_assignment_requested_topic(self, monkeypatch):
            # - Arrange -
            mock_producer = AsyncMock()
            mock_producer.send.return_value = MagicMock()
            monkeypatch.setattr(kafka_client, "get_producer", lambda: mock_producer)

            request = TruckAssignmentRequest(delivery_id="delivery-abc123", cargo_weight_kg=700)

            # - Act -
            asyncio.run(assignment_producer.produce_truck_assignment_requested(request))

            # - Assert Result -
            # No return value, no assertions needed

            # - Assert mock calls -
            mock_producer.send.assert_awaited_once_with(
                "truck-assignment-requested",
                key="delivery-abc123",
                value=request.model_dump(),
            )

        def test_registers_log_send_failure_as_the_futures_done_callback(self, monkeypatch):
            # - Arrange -
            mock_producer = AsyncMock()
            mock_future = MagicMock()
            mock_producer.send.return_value = mock_future
            monkeypatch.setattr(kafka_client, "get_producer", lambda: mock_producer)

            request = TruckAssignmentRequest(delivery_id="delivery-abc123", cargo_weight_kg=700)

            # - Act -
            asyncio.run(assignment_producer.produce_truck_assignment_requested(request))

            # - Assert Result -
            # No return value, no assertions needed

            # - Assert mock calls -
            mock_future.add_done_callback.assert_called_once()
            callback = mock_future.add_done_callback.call_args.args[0]
            assert callback.func is kafka_client.log_send_failure
            assert callback.args == ("truck-assignment-requested", "delivery-abc123")

class TestLogSendFailure:
    def test_logs_error_when_future_resolved_with_exception(self, caplog):
        # - Arrange -
        future = asyncio.new_event_loop().create_future()
        error = RuntimeError("broker unavailable")
        future.set_exception(error)

        # - Act -
        with caplog.at_level(logging.ERROR):
            kafka_client.log_send_failure("truck-assignment-requested", "delivery-abc123", future)

        # - Assert Result -
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelno == logging.ERROR
        assert "truck-assignment-requested" in record.getMessage()
        assert "delivery-abc123" in record.getMessage()
        assert record.exc_info[1] is error

    def test_does_not_log_when_future_resolved_without_exception(self, caplog):
        # - Arrange -
        future = asyncio.new_event_loop().create_future()
        future.set_result(None)

        # - Act -
        with caplog.at_level(logging.ERROR):
            kafka_client.log_send_failure("truck-assignment-requested", "delivery-abc123", future)

        # - Assert Result -
        assert caplog.records == []
