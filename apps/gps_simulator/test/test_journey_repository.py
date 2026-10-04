from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.models.journey import Journey
from app.models.truck_departure import Coordinates
from app.repositories import journey_repository


def _get_journey(**overrides):
    defaults = dict(
        delivery_id='delivery-123',
        truck_id='truck-987',
        pickup_location=Coordinates(lon=48.8566, lat=2.3522),
        dropoff_location=Coordinates(lon=47.2184, lat=-1.5536),
        departure_time=datetime.now(timezone.utc) + timedelta(hours=2),
    )

    defaults.update(overrides)
    return Journey(**defaults)


@pytest_asyncio.fixture(autouse=True, loop_scope="module")
async def clear_repository(postgres_db):
    await journey_repository.clear()


@pytest.mark.repository
@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
class TestJourneyRepository:
    async def test_get_journeys_returns_all_saved_journeys(self):
        # - Arrange -
        journeys = [
            _get_journey(),
            _get_journey(delivery_id='delivery-456'),
        ]

        for journey in journeys:
            await journey_repository.save_journey(journey)

        # - Act -
        result = await journey_repository.get_journeys()

        # - Assert -
        assert len(result) == len(journeys)
        assert result == journeys

    async def test_get_journey_by_delivery_id_returns_correct_journey(self):
        # - Arrange -
        journeys = [
            _get_journey(),
            _get_journey(delivery_id='delivery-456'),
        ]

        for journey in journeys:
            await journey_repository.save_journey(journey)

        # - Act -
        missing = await journey_repository.get_journey_by_delivery_id("delivery-111")
        found = await journey_repository.get_journey_by_delivery_id("delivery-456")

        # - Assert -
        assert missing is None
        assert found == journeys[1]

    async def test_save_journey_twice_updates_journey(self):
        # - Arrange -
        journeys = [
            _get_journey(),
            _get_journey(truck_id='truck-456'),
        ]

        for journey in journeys:
            await journey_repository.save_journey(journey)

        # - Act -
        journey = await journey_repository.get_journey_by_delivery_id("delivery-123")
        saved_journeys = await journey_repository.get_journeys()

        # - Assert -
        assert journey is not None
        assert journey == journeys[1]
        assert len(saved_journeys) == 1  # No duplication
