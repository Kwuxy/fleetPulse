import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.clients.kafka_client import QueueMessageStatus
from app.consumers import departure_consumer
from app.models.truck_departure import TruckDepartureScheduled, Coordinates
from app.services import journey_service


def _get_truck_departure_scheduled_message():
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
@pytest.mark.unit
class TestDepartureConsumer:
    class TestBuildTruckDepartureScheduled:
        def test_building_truck_departure_scheduled_success_on_valid_message(self):
            # - Arrange -
            msg = _get_truck_departure_scheduled_message()

            # - Act -
            result = departure_consumer._build_truck_departure_scheduled(msg)

            # - Assert Result -
            assert result == _get_truck_departure_scheduled()

        def test_building_truck_departure_scheduled_rejects_on_incomplete_message(self):
            # - Arrange -
            msg = {"delivery_id": "delivery-abc123"}  # missing required fields

            # - Act & Assert -
            with pytest.raises(ValidationError):
                departure_consumer._build_truck_departure_scheduled(msg)

            # - Assert Result -
            # Exception raised, no assertions needed

    class TestHandleTruckDepartureScheduled:
        def test_creates_journey_and_returns_consumed_on_valid_message(self, monkeypatch):
            # - Arrange -
            mock_create_journey = AsyncMock()
            monkeypatch.setattr(journey_service, "create_journey", mock_create_journey)

            msg = _get_truck_departure_scheduled_message()

            # - Act -
            result = asyncio.run(departure_consumer.handle_truck_departure_scheduled(msg))

            # - Assert Result -
            assert result == QueueMessageStatus.CONSUMED

            # - Assert mock calls -
            mock_create_journey.assert_awaited_once_with(_get_truck_departure_scheduled())

        def test_returns_consumed_without_creating_journey_on_malformed_message(self, monkeypatch):
            # - Arrange -
            mock_create_journey = AsyncMock()
            monkeypatch.setattr(journey_service, "create_journey", mock_create_journey)

            msg = {"delivery_id": "delivery-abc123"}  # missing required fields

            # - Act -
            result = asyncio.run(departure_consumer.handle_truck_departure_scheduled(msg))

            # - Assert Result -
            assert result == QueueMessageStatus.CONSUMED

            # - Assert mock calls -
            mock_create_journey.assert_not_awaited()
