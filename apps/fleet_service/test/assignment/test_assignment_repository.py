import pytest
import pytest_asyncio

from app.models.truck import Truck, TruckStatus
from app.repositories import assignment_repository, truck_repository


def _get_truck(**overrides):
    defaults = dict(
        id="truck-123",
        plate_number="AB-123-CD",
        capacity_kg=1200,
        status=TruckStatus.AVAILABLE
    )
    defaults.update(overrides)
    return Truck(**defaults)


trucks_catalog = [
    {'id': "truck-small", 'plate_number': "AV-123-SM", 'capacity_kg': 100, 'status': TruckStatus.AVAILABLE},
    {'id': "truck-large", 'plate_number': "AV-845-LG", 'capacity_kg': 3000, 'status': TruckStatus.AVAILABLE},
    {'id': "truck-medium", 'plate_number': "AV-001-MD", 'capacity_kg': 1200, 'status': TruckStatus.AVAILABLE},
    {'id': "truck-use", 'plate_number': "IU-999-MD", 'capacity_kg': 1200, 'status': TruckStatus.IN_USE},
    {'id': "truck-repair", 'plate_number': "RE-932-MD", 'capacity_kg': 1200, 'status': TruckStatus.IN_REPAIR},
]


def _get_trucks(truck_list: list[str]) -> dict[str, Truck]:
    return {
        str(overrides['id']): _get_truck(**overrides) for overrides in trucks_catalog
        if overrides['id'] in truck_list
    }


async def init_trucks(truck_list: list[str]) -> dict[str, Truck]:
    # Save in database a list of trucks for usage in test
    trucks = _get_trucks(truck_list)
    for truck in trucks.values():
        await truck_repository.save_truck(truck)

    return trucks


@pytest_asyncio.fixture(autouse=True, loop_scope="module")
async def clear_repository(postgres_db):
    await truck_repository.clear()


@pytest.mark.repository
@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
class TestAssignmentRepository:
    async def test_find_available_truck_for_capacity_returns_smallest_sufficient_truck(self):
        # - Arrange -
        trucks = await init_trucks(['truck-small', 'truck-medium', 'truck-large'])

        # - Act -
        truck = await assignment_repository.find_available_truck_for_capacity(50)

        # - Assert -
        assert truck == trucks['truck-small']

    async def test_find_available_truck_for_capacity_ignores_trucks_with_insufficient_capacity(self):
        # - Arrange -
        trucks = await init_trucks(['truck-small', 'truck-medium', 'truck-large'])

        # - Act -
        truck = await assignment_repository.find_available_truck_for_capacity(1200)

        # - Assert -
        assert truck == trucks['truck-medium']

    async def test_find_available_truck_for_capacity_ignores_trucks_in_use(self):
        # - Arrange -
        trucks = await init_trucks(['truck-small', 'truck-use', 'truck-large'])

        # - Act -
        truck = await assignment_repository.find_available_truck_for_capacity(700)

        # - Assert -
        assert truck == trucks['truck-large']

    async def test_find_available_truck_for_capacity_ignores_trucks_in_repair(self):
        # - Arrange -
        trucks = await init_trucks(['truck-small', 'truck-repair', 'truck-large'])

        # - Act -
        truck = await assignment_repository.find_available_truck_for_capacity(700)

        # - Assert -
        assert truck == trucks['truck-large']

    async def test_find_available_truck_for_capacity_returns_none_when_no_truck_is_available(self):
        # - Arrange -
        _ = await init_trucks(['truck-use'])

        # - Act -
        truck = await assignment_repository.find_available_truck_for_capacity(700)

        # - Assert -
        assert truck is None
