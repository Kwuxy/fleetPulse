from apps.fleet_service.app.models.truck import Truck, TruckStatus
from apps.fleet_service.app.repositories import truck_repository


def find_available_truck_for_capacity(min_capacity_kg: int) -> Truck | None:
    trucks = [
        truck
        for truck in truck_repository.get_trucks()
        if truck.status == TruckStatus.AVAILABLE
           and truck.capacity_kg >= min_capacity_kg
    ]

    truck = min(trucks, key=lambda t: t.capacity_kg, default=None)
    return truck