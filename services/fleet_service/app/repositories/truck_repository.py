from services.fleet_service.app.models.truck import Truck

_trucks: dict[str, Truck] = {}

def save_truck(truck: Truck) -> None:
    _trucks[truck.id] = truck

def get_trucks() -> list[Truck]:
    return list(_trucks.values())

def clear() -> None:
    _trucks.clear()

def get_truck_by_plate_number(plate_number: str) -> Truck | None:
    truck_by_plate_number = filter(lambda t: t.plate_number == plate_number, list(_trucks.values()))
    truck = next(truck_by_plate_number, None)
    return truck
