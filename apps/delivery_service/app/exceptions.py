from datetime import date


class InvalidClient(Exception):
    def __init__(self, client_id: int):
        super().__init__(f"Client with id {client_id} does not exist")

class SameLocationsException(Exception):
    def __init__(self):
        super().__init__("Pickup and dropoff locations cannot be the same")

class InvalidCargo(Exception):
    def __init__(self, cargo_weight_kg: int):
        super().__init__(f"Invalid cargo weight: {cargo_weight_kg} kg. Cargo weight must be greater than 0.")

class InvalidRequestedDate(Exception):
    def __init__(self, requested_date: date):
        super().__init__(f"Invalid requested date: {requested_date}. Requested date must be in the future.")

class NotFoundException(Exception):
    def __init__(self, delivery_id: str):
        super().__init__(f"Delivery not found: {delivery_id}")

class OSRMRequestFailed(Exception):
    def __init__(self, msg: str):
        super().__init__(msg)

class UnknownCity(Exception):
    def __init__(self, city_name: str):
        super().__init__(f"Unknown city `{city_name}` in osrm_client config")

class UnassignedTruckOnCompletedAssignment(Exception):
    def __init__(self, delivery_id: str):
        super().__init__(f"Delivery {delivery_id} has no assigned truck")
