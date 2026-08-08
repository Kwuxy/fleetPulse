from services.fleet_service.app.models.truck import Truck

trucks: dict[str, Truck] = {}

def save_truck(truck: Truck):
    trucks[truck.id] = truck

def get_trucks() -> list[Truck]:
    return list(trucks.values())
