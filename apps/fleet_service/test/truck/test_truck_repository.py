import pytest
import pytest_asyncio

from app.models.truck import Truck, TruckStatus
from app.repositories import truck_repository


@pytest_asyncio.fixture(autouse=True, loop_scope="module")
async def clear_repository(postgres_db):
    await truck_repository.clear()


@pytest.mark.repository
@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
class TestTruckRepository:
    async def test_save_truck_stores_truck(self):
        # - Arrange -
        truck = self._get_truck()
        await truck_repository.save_truck(truck)

        # - Act -
        trucks = await truck_repository.get_trucks()

        # - Assert -
        assert trucks == [truck]

    async def test_get_trucks_by_plate_number(self):
        # - Arrange -
        truck = self._get_truck()
        t = await truck_repository.get_truck_by_plate_number(truck.plate_number)
        assert t is None

        await truck_repository.save_truck(truck)

        # - Act -
        t = await truck_repository.get_truck_by_plate_number(truck.plate_number)

        # - Assert -
        assert t == truck

    @staticmethod
    def _get_truck(**overrides):
        defaults = dict(
            id="truck-123",
            plate_number="AB-123-CD",
            capacity_kg=1200,
            status=TruckStatus.AVAILABLE
        )
        defaults.update(overrides)
        return Truck(**defaults)
