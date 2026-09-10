import asyncio
import os
import random
from datetime import date, timedelta
from functools import cache
from pathlib import Path

from tqdm import tqdm

from app.clients import db_client
from app.services import delivery_service
from app.models.delivery import Delivery, DeliveryStatus, DeliveryDenialReason
from app.repositories import delivery_repository

LOCATIONS = ['Paris', 'Berlin', 'Brussels', 'Lyon', 'Madrid', 'Rome', 'Nantes', 'Toulouse', 'Strasbourg', 'Marseille',
             'Bordeaux']

TRUCK_IDS = [
    'truck-da6f3a40', 'truck-ba3d9504', 'truck-35e93dbe', 'truck-cad42173', 'truck-f1d26e15', 'truck-06d09bd8', 'truck-a246a51b', 'truck-c301f5bb', 'truck-6ba6c790', 'truck-2bc9d5f6',
    'truck-1d60d627', 'truck-d4a58aae', 'truck-472b58ec', 'truck-d519b4dc', 'truck-2e240760', 'truck-53b136bc', 'truck-805abea5', 'truck-a792a9fd', 'truck-807743c8', 'truck-b9e83d06',
    'truck-83a7050e', 'truck-3f814473', 'truck-dd547d81', 'truck-0852625c', 'truck-c1c98eb8', 'truck-ec7e03a5', 'truck-53ee7ba0', 'truck-7a1f796b', 'truck-4a086d09', 'truck-27f381f1',
    'truck-0e14f4ff', 'truck-0086daaf', 'truck-52933741', 'truck-1c535125', 'truck-92b7f00c', 'truck-262fddca', 'truck-b7e33a68', 'truck-e41275b6', 'truck-c656ef19', 'truck-4cf6aff5',
    'truck-7b8d235e', 'truck-555ff78e', 'truck-13733cc8', 'truck-5aae6554', 'truck-16c20327', 'truck-7aaf11bd', 'truck-cba9b7c9', 'truck-e2578ffa', 'truck-f47b8a5c', 'truck-25cad042',
]

# Should match fleet_service seed_data.py repartition
WEIGHT_REPARTITION = [(0.3, 'small'), (0.6, 'medium'), (0.9, 'large'), (1.0, 'xxl')]
DENIAL_REPARTITION = [
    (0.33, DeliveryDenialReason.INVALID_REQUEST, 'Delivery not found.'),
    (0.66, DeliveryDenialReason.INVALID_REQUEST, 'Invalid cargo weight. Must be greater than 0.'),
    (1, DeliveryDenialReason.NO_AVAILABLE_TRUCK, 'No truck available.'),
]


def _get_delivery_cargo_weight_kg(size: str) -> int:
    match size:
        case 'small':
            return 100
        case 'medium':
            return 500
        case 'large':
            return 1000
        case 'xxl':
            return 5000
        case _:
            raise ValueError(f"Invalid size: {size}")


def _override_env_variables() -> None:
    # Override the default .env file
    from dotenv import dotenv_values
    env_values = dotenv_values(Path(__file__).parents[3] / ".env")  # repo root
    os.environ.setdefault("POSTGRES_USER", env_values.get("DELIVERY_SERVICE_DB_USER") or "POPULATE .env file")
    os.environ.setdefault("POSTGRES_PASSWORD", env_values.get("DELIVERY_SERVICE_DB_PASSWORD") or "POPULATE .env file")
    os.environ.setdefault("POSTGRES_DB", env_values.get("DELIVERY_SERVICE_DB_NAME") or "POPULATE .env file")


@cache
def _get_location_pairs() -> list[dict[str, str]]:
    return [
        {'pickup': LOCATIONS[pickup], 'dropoff': LOCATIONS[dropoff]}
        for pickup in range(len(LOCATIONS))
        for dropoff in range(len(LOCATIONS))
        if pickup != dropoff
    ]


def _get_location_pair() -> dict[str, str]:
    location_pairs = _get_location_pairs()
    return location_pairs[random.randint(0, len(location_pairs) - 1)]


def _get_deliveries(nb: int, **overrides) -> list[Delivery]:
    res = []
    for i in range(nb):
        locations = _get_location_pair()
        weight_type = [x[1] for x in WEIGHT_REPARTITION if x[0] > i / nb][0]
        denial_type = [{'reason': x[1], 'description': x[2]} for x in DENIAL_REPARTITION if x[0] > i / nb][0]
        default = {
            'id': delivery_service._generate_delivery_id(),
            'client_id': _generate_client_id(),
            'pickup_location': locations['pickup'],
            'dropoff_location': locations['dropoff'],
            'cargo_weight_kg': _get_delivery_cargo_weight_kg(weight_type),
            'requested_date': date.today() + timedelta(days=1),
            'status': DeliveryStatus.REQUESTED,
            'assigned_truck_id': None,
            'denial_reason': None,
            'denial_description': None,
        }
        default.update(overrides)

        match default['status']:
            case DeliveryStatus.ASSIGNED:
                default['assigned_truck_id'] = _get_next_truck_id()
            case DeliveryStatus.COMPLETED:
                default['assigned_truck_id'] = _get_next_truck_id()
                default['requested_date'] = date.today() - timedelta(days=1)
            case DeliveryStatus.DENIED:
                default['denial_reason'] = denial_type['reason']
                default['denial_description'] = denial_type['description']

        res.append(Delivery(**default))
    return res


def _get_requested_deliveries() -> list[Delivery]:
    return _get_deliveries(nb=10, status=DeliveryStatus.REQUESTED, assigned_truck_id=None)


def _get_assigned_deliveries() -> list[Delivery]:
    return _get_deliveries(nb=40, status=DeliveryStatus.ASSIGNED, assigned_truck_id=None)


def _get_denied_deliveries() -> list[Delivery]:
    return _get_deliveries(nb=10, status=DeliveryStatus.DENIED, assigned_truck_id=None)


def _get_completed_deliveries() -> list[Delivery]:
    return _get_deliveries(nb=10, status=DeliveryStatus.COMPLETED, assigned_truck_id=None)


async def _seed_data():
    _override_env_variables()
    await db_client.start_db()
    try:
        await delivery_repository.clear()

        deliveries = [*_get_requested_deliveries(), *_get_assigned_deliveries(), *_get_denied_deliveries(),
                      *_get_completed_deliveries()]

        for delivery in tqdm(deliveries, desc="Seeding deliveries"):
            await delivery_repository.save_delivery(delivery)
    finally:
        await db_client.stop_db()


def _generate_client_id():
    return random.randint(10000, 99999)


def _get_next_truck_id():
    if len(TRUCK_IDS) == 0:
        raise ValueError("No more trucks available")

    return TRUCK_IDS.pop(0)


if __name__ == "__main__":
    print("Starting seeding delivery data...")
    asyncio.run(_seed_data())
