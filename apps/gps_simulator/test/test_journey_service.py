import asyncio
from datetime import timedelta, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.repositories import journey_repository
from app.services import journey_service
from app.models.truck_departure import TruckDepartureScheduled, Coordinates


@pytest.mark.service
@pytest.mark.unit
class TestJourneyService:
    @pytest.fixture()
    def mock_save_journey(self, monkeypatch):
        mock = AsyncMock()
        monkeypatch.setattr(journey_repository, "save_journey", mock)
        return mock

    class TestCreateJourney:
        @staticmethod
        def _get_create_truck_departure_scheduled(**overrides) -> TruckDepartureScheduled:
            defaults = dict(
                delivery_id='delivery-123',
                truck_id='truck-987',
                pickup_location=Coordinates(lon=48.8566, lat=2.3522),
                dropoff_location=Coordinates(lon=47.2184, lat=-1.5536),
                departure_time=datetime.now(timezone.utc) + timedelta(hours=2),
            )
            defaults.update(overrides)
            return TruckDepartureScheduled(**defaults)

        def test_create_journey_calls_repository_save(self, mock_save_journey):
            # - Arrange -
            request = self._get_create_truck_departure_scheduled()

            # - Act -
            journey = asyncio.run(journey_service.create_journey(request))

            # - Assert Result -
            assert journey.delivery_id == request.delivery_id
            assert journey.truck_id == request.truck_id
            assert journey.pickup_location == request.pickup_location
            assert journey.dropoff_location == request.dropoff_location
            assert journey.departure_time == request.departure_time

            # - Assert mock calls -
            mock_save_journey.assert_awaited_once_with(journey)
