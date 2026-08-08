from services.fleet_service.app.models.truck import Truck

_trucks: dict[str, Truck] = {}

def save_truck(truck: Truck) -> None:
    _trucks[truck.id] = truck

def get_trucks() -> list[Truck]:
    return list(_trucks.values())

def clear() -> None:
    _trucks.clear()
