import asyncio
import os
import random
import subprocess
from pathlib import Path

from tqdm import tqdm

from app.services import truck_service
from app.repositories import truck_repository
from app.clients import db_client
from app.models.truck import Truck, TruckStatus

IN_USE_TRUCK_IDS = [
    'truck-da6f3a40', 'truck-ba3d9504', 'truck-35e93dbe', 'truck-cad42173', 'truck-f1d26e15', 'truck-06d09bd8', 'truck-a246a51b', 'truck-c301f5bb', 'truck-6ba6c790', 'truck-2bc9d5f6',
    'truck-1d60d627', 'truck-d4a58aae', 'truck-472b58ec', 'truck-d519b4dc', 'truck-2e240760', 'truck-53b136bc', 'truck-805abea5', 'truck-a792a9fd', 'truck-807743c8', 'truck-b9e83d06',
    'truck-83a7050e', 'truck-3f814473', 'truck-dd547d81', 'truck-0852625c', 'truck-c1c98eb8', 'truck-ec7e03a5', 'truck-53ee7ba0', 'truck-7a1f796b', 'truck-4a086d09', 'truck-27f381f1',
    'truck-0e14f4ff', 'truck-0086daaf', 'truck-52933741', 'truck-1c535125', 'truck-92b7f00c', 'truck-262fddca', 'truck-b7e33a68', 'truck-e41275b6', 'truck-c656ef19', 'truck-4cf6aff5',
    'truck-7b8d235e', 'truck-555ff78e', 'truck-13733cc8', 'truck-5aae6554', 'truck-16c20327', 'truck-7aaf11bd', 'truck-cba9b7c9', 'truck-e2578ffa', 'truck-f47b8a5c', 'truck-25cad042',
]

# Should match fleet_service seed_data.py repartition
WEIGHT_REPARTITION = [(0.3, 'small'), (0.6, 'medium'), (0.9, 'large'), (1.0, 'xxl')]


def _get_truck_cargo_weight_kg(size: str) -> int:
    match size:
        case 'small':
            return random.randint(100, 400)
        case 'medium':
            return random.randint(500, 900)
        case 'large':
            return random.randint(1000, 3500)
        case 'xxl':
            return random.randint(5000, 10000)
        case _:
            raise ValueError(f"Invalid size: {size}")


def _override_env_variables() -> None:
    if os.environ.get('POSTGRES_USER') is not None:
        return

    # Override the default .env file
    from dotenv import dotenv_values
    env_values = dotenv_values(Path(__file__).parents[3] / ".env")  # repo root
    os.environ.setdefault("POSTGRES_USER", env_values.get("FLEET_SERVICE_DB_USER") or "POPULATE .env file")
    os.environ.setdefault("POSTGRES_PASSWORD", env_values.get("FLEET_SERVICE_DB_PASSWORD") or "POPULATE .env file")
    os.environ.setdefault("POSTGRES_DB", env_values.get("FLEET_SERVICE_DB_NAME") or "POPULATE .env file")


def _get_trucks(nb: int, id_type: str= 'generate', **overrides) -> list[Truck]:
    res = []
    for i in range(nb):
        weight_type = [x[1] for x in WEIGHT_REPARTITION if x[0] > i / nb][0]
        truck_id = _get_next_truck_id() if id_type == 'pre-generated' else truck_service._generate_truck_id()
        default = {
            'id': truck_id,
            'plate_number': _generate_truck_plate_number(),
            'capacity_kg': _get_truck_cargo_weight_kg(weight_type),
            'status': TruckStatus.AVAILABLE,
        }
        default.update(overrides)
        res.append(Truck(**default))
    return res

def _get_available_trucks() -> list[Truck]:
    return _get_trucks(nb=10, status=TruckStatus.AVAILABLE)

def _get_in_use_trucks() -> list[Truck]:
    return _get_trucks(nb=40, id_type='pre-generated', status=TruckStatus.IN_USE)

def _get_in_repair_trucks() -> list[Truck]:
    return _get_trucks(nb=10, status=TruckStatus.IN_REPAIR)

def get_fill_trucks() -> list[Truck]:
    return _get_trucks(nb=10, id_type='pre-generated', status=TruckStatus.AVAILABLE)


async def _seed_data():
    _override_env_variables()
    await db_client.start_db()
    try:
        await truck_repository.clear()

        trucks = [*_get_available_trucks(), *_get_in_use_trucks(), *_get_in_repair_trucks(), *get_fill_trucks()]

        for truck in tqdm(trucks, desc="Seeding trucks"):
            await truck_repository.save_truck(truck)
    finally:
        await db_client.stop_db()


def _generate_truck_plate_number():
    def _generate_letters_group():
        letters = [chr(ord('A') + random.randint(0, 25)) for _ in range(2)]
        return f'{letters[0]}{letters[1]}'

    def _generate_numbers_group():
        numbers = [str(random.randint(0, 9)) for _ in range(3)]
        return ''.join(numbers)

    return f"{_generate_letters_group()}-{_generate_numbers_group()}-{_generate_letters_group()}"


def _get_next_truck_id() -> str:
    if len(IN_USE_TRUCK_IDS) == 0:
        raise ValueError("No more trucks available")

    return IN_USE_TRUCK_IDS.pop(0)


def _generate_ids(nb: int = 10):
    ids = ', '.join([f"'{truck_service._generate_truck_id()}'" for _ in range(nb)])
    print(f"\tTruck IDs: {ids}")
    subprocess.run("clip", input=f'[{ids}]'.encode("utf-16-le"), check=True)
    print('Ids copied to clipboard.')


def _parse_args():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate_ids", "-ids", type=int, help="Number of IDs to generate")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.generate_ids:
        print(f"Generating {args.generate_ids} IDs...")
        _generate_ids(args.generate_ids)
        exit(0)

    print("Starting seeding truck data...")
    asyncio.run(_seed_data())