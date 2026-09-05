from app.repositories import truck_repository
from app.models.truck import Truck, TruckStatus


async def find_available_truck_for_capacity(min_capacity_kg: int) -> Truck | None:
    trucks = [
        truck
        for truck in await truck_repository.get_trucks()
        if truck.status == TruckStatus.AVAILABLE
           and truck.capacity_kg >= min_capacity_kg
    ]

    truck = min(trucks, key=lambda t: t.capacity_kg, default=None)
    return truck