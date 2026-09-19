import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.clients import kafka_client
from app.models.truck_departure import TruckDepartureScheduled, Coordinates
from app.producers import departure_producer


@pytest.mark.unit
@pytest.mark.kafka
class TestDepartureProducer:
    class TestProduceDeliveryScheduled:
        def test_sends_scheduled_message_to_truck_departure_scheduled_topic(self, monkeypatch):
            # - Arrange -
            mock_producer = AsyncMock()
            mock_producer.send.return_value = MagicMock()
            monkeypatch.setattr(kafka_client, "get_producer", lambda: mock_producer)

            request = TruckDepartureScheduled(
                delivery_id="delivery-abc123",
                truck_id="truck-zyx987",
                pickup_location=Coordinates(lat=123.456, lon=789.012),
                dropoff_location=Coordinates(lat=456.789, lon=123.456),
                departure_time=datetime.now() + timedelta(minutes=50),
            )

            # - Act -
            asyncio.run(departure_producer.produce_truck_departure_scheduled(request))

            # - Assert Result -
            # No return value, no assertions needed

            # - Assert mock calls -
            mock_producer.send.assert_awaited_once_with(
                "delivery-departure-scheduled",
                key="delivery-abc123",
                value=request.model_dump(mode="json"),
            )

        def test_registers_log_send_failure_as_the_futures_done_callback(self, monkeypatch):
            # - Arrange -
            mock_producer = AsyncMock()
            mock_future = MagicMock()
            mock_producer.send.return_value = mock_future
            monkeypatch.setattr(kafka_client, "get_producer", lambda: mock_producer)

            request = TruckDepartureScheduled(
                delivery_id="delivery-abc123",
                truck_id="truck-zyx987",
                pickup_location=Coordinates(lat=123.456, lon=789.012),
                dropoff_location=Coordinates(lat=456.789, lon=123.456),
                departure_time=datetime.now() + timedelta(minutes=50),
            )

            # - Act -
            asyncio.run(departure_producer.produce_truck_departure_scheduled(request))

            # - Assert Result -
            # No return value, no assertions needed

            # - Assert mock calls -
            mock_future.add_done_callback.assert_called_once()
            callback = mock_future.add_done_callback.call_args.args[0]
            assert callback.func is kafka_client.log_send_failure
            assert callback.args == ("truck-assignment-requested", "delivery-abc123")

