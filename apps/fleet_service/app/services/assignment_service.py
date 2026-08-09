from apps.fleet_service.app.exceptions import UnknownDelivery, InvalidCargoWeight, NoTruckAvailable
from apps.fleet_service.app.models.assignment import TruckAssignmentRequest
from apps.fleet_service.app.models.truck import Truck, TruckStatus
from apps.fleet_service.app.repositories import assignment_repository, truck_repository


def assign_truck_to_delivery(request: TruckAssignmentRequest) -> Truck:
    if not _is_valid_delivery(request.delivery_id):
        raise UnknownDelivery(request.delivery_id)

    if not _is_valid_cargo_weight(request.cargo_weight_kg):
        raise InvalidCargoWeight(request.cargo_weight_kg)

    truck = assignment_repository.find_available_truck_for_capacity(request.cargo_weight_kg)
    if truck is None:
        raise NoTruckAvailable(request.cargo_weight_kg)

    truck.status = TruckStatus.IN_USE
    truck_repository.save_truck(truck)

    return truck

def _is_valid_delivery(delivery_id: str):
    return True  # TODO : Implement delivery validation

def _is_valid_cargo_weight(cargo_weight_kg: int):
    return cargo_weight_kg > 0
