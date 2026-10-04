import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, call

import pytest

from app.clients import kafka_client
from app.consumers.departure_consumer import handle_truck_departure_scheduled
from app.models.truck_departure import TruckDepartureScheduled, Coordinates
from app.services import journey_service


def _get_truck_departure_scheduled_message():
    # Raw wire format, as Delivery Service's departure_producer sends it
    # (model_dump(mode="json") -> departure_time is an ISO 8601 string)
    return {
        "delivery_id": "delivery-abc123",
        "truck_id": "truck-zyx987",
        "pickup_location": {"lat": 48.8566, "lon": 2.3522},
        "dropoff_location": {"lat": 45.764, "lon": 4.8357},
        "departure_time": "2026-09-20T10:00:00",
    }


def _get_truck_departure_scheduled():
    return TruckDepartureScheduled(
        delivery_id="delivery-abc123",
        truck_id="truck-zyx987",
        pickup_location=Coordinates(lat=48.8566, lon=2.3522),
        dropoff_location=Coordinates(lat=45.764, lon=4.8357),
        departure_time=datetime(2026, 9, 20, 10, 0, 0),
    )


@pytest.mark.kafka
@pytest.mark.integration
@pytest.mark.asyncio
class TestDepartureKafkaIntegration:
    async def test_departure_scheduled_message_creates_journey_via_service(self, monkeypatch, kafka_producer):
        # - Arrange -
        mock_create_journey = AsyncMock()
        monkeypatch.setattr(journey_service, "create_journey", mock_create_journey)
        departure_msg = _get_truck_departure_scheduled_message()

        # - Act -
        await kafka_producer.send_and_wait(
            "truck-departure-scheduled",
            key=departure_msg["delivery_id"],
            value=departure_msg,
        )

        await asyncio.wait_for(_wait_for_await_count(mock_create_journey, 1), timeout=15)

        # - Assert result -
        # No message produced, no assertions needed

        # - Assert mock -
        mock_create_journey.assert_awaited_once_with(_get_truck_departure_scheduled())

    async def test_message_is_redelivered_after_handler_raises_an_uncaught_exception(self, monkeypatch,
                                                                                     kafka_producer):
        # - Arrange -
        mock_create_journey = AsyncMock(side_effect=[RuntimeError("Mocked exception"), None])
        monkeypatch.setattr(journey_service, "create_journey", mock_create_journey)
        departure_msg = _get_truck_departure_scheduled_message()

        # - Act -
        await kafka_producer.send_and_wait(
            "truck-departure-scheduled",
            key=departure_msg["delivery_id"],
            value=departure_msg,
        )

        await asyncio.wait_for(_wait_for_await_count(mock_create_journey, 1), timeout=15)
        await restart_kafka_client()
        await asyncio.wait_for(_wait_for_await_count(mock_create_journey, 2), timeout=15)
        await asyncio.sleep(0.5)  # Waiting for the message to be committed, so it doesn't leak into the next test

        # - Assert result -
        # No message produced, no assertions needed

        # - Assert mock -
        assert mock_create_journey.await_count == 2
        mock_create_journey.assert_has_awaits(
            [call(_get_truck_departure_scheduled()), call(_get_truck_departure_scheduled())])

    async def test_offset_is_committed_after_successful_handling_so_message_is_not_redelivered(self, monkeypatch,
                                                                                               kafka_producer):
        # - Arrange -
        mock_create_journey = AsyncMock()
        monkeypatch.setattr(journey_service, "create_journey", mock_create_journey)
        departure_msg = _get_truck_departure_scheduled_message()

        # - Act -
        await kafka_producer.send_and_wait(
            "truck-departure-scheduled",
            key=departure_msg["delivery_id"],
            value=departure_msg,
        )

        await asyncio.wait_for(_wait_for_await_count(mock_create_journey, 1), timeout=15)
        await asyncio.sleep(0.5)  # Waiting for the message to be committed, avoid race condition

        await restart_kafka_client()
        await asyncio.sleep(1)  # Giving time to kafka to redeliver the message

        # - Assert result -
        # No message produced, no assertions needed

        # - Assert mock -
        mock_create_journey.assert_awaited_once_with(_get_truck_departure_scheduled())

    async def test_malformed_departure_scheduled_message_is_dropped_without_creating_journey(self, monkeypatch,
                                                                                             kafka_producer):
        # - Arrange -
        mock_create_journey = AsyncMock()
        monkeypatch.setattr(journey_service, "create_journey", mock_create_journey)
        departure_msg = _get_truck_departure_scheduled_message()
        del departure_msg["departure_time"]  # Missing required `departure_time`

        # - Act -
        await kafka_producer.send_and_wait(
            "truck-departure-scheduled",
            key=departure_msg["delivery_id"],
            value=departure_msg,
        )

        await asyncio.sleep(1)  # give the consumer a chance to fetch and process a message if any

        # - Assert result -
        # No message produced, no assertions needed

        # - Assert mock -
        mock_create_journey.assert_not_awaited()


async def _wait_for_await_count(mock, count):
    while mock.await_count < count:
        await asyncio.sleep(0.1)


async def restart_kafka_client():
    # Manually "restart" the consuming loop to simulate a restart of the consumer
    await kafka_client.stop_consuming()
    await kafka_client.start_consuming(handle_truck_departure_scheduled)
