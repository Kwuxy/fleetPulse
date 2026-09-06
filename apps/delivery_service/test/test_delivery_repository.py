from datetime import date, timedelta

import pytest
import pytest_asyncio

from app.models.delivery import Delivery, DeliveryStatus
from app.repositories import delivery_repository


def _get_delivery(**overrides):
    defaults = dict(
        id='delivery-123',
        client_id=23,
        pickup_location="Test Location",
        dropoff_location="Test Destination",
        cargo_weight_kg=200,
        requested_date=(date.today() + timedelta(days=1)),
        status=DeliveryStatus.REQUESTED,
        assigned_truck_id=None
    )

    defaults.update(overrides)
    return Delivery(**defaults)


@pytest_asyncio.fixture(autouse=True, loop_scope="module")
async def clear_repository(postgres_db):
    await delivery_repository.clear()


@pytest.mark.repository
@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
class TestDeliveryRepository:
    async def test_save_delivery_returns_correct_delivery(self):
        # - Arrange -
        deliveries = [
            _get_delivery(),
            _get_delivery(id='delivery-456', status=DeliveryStatus.ASSIGNED, assigned_truck_id="truck-7894"),
        ]

        for delivery in deliveries:
            await delivery_repository.save_delivery(delivery)

        # - Act -
        result = await delivery_repository.get_deliveries()

        # - Assert -
        assert len(result) == len(deliveries)
        assert result == deliveries

    async def test_get_delivery_by_id_returns_correct_delivery(self):
        # - Arrange -
        deliveries = [
            _get_delivery(),
            _get_delivery(id='delivery-456', status=DeliveryStatus.ASSIGNED, assigned_truck_id="truck-7894"),
        ]

        for delivery in deliveries:
            await delivery_repository.save_delivery(delivery)

        # - Act -
        missing = await delivery_repository.get_delivery_by_id("delivery-111")
        found = await delivery_repository.get_delivery_by_id("delivery-456")

        # - Assert -
        assert missing is None
        assert found == deliveries[1]
