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