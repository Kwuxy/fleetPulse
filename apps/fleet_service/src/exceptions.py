class InvalidTruckCapacity(Exception):
    def __init__(self, capacity: int):
        super().__init__(f"Invalid truck capacity: {capacity} kg")

class InvalidPlateNumber(Exception):
    def __init__(self, plate_number: str):
        super().__init__(f"Invalid plate number: {plate_number}")

class DuplicatePlateNumber(Exception):
    def __init__(self, plate_number: str):
        super().__init__(f"Plate number already exists: {plate_number}")

class UnknownDelivery(Exception):
    def __init__(self, delivery_id: str):
        super().__init__(f"Delivery with id {delivery_id} not found")

class InvalidCargoWeight(Exception):
    def __init__(self, cargo_weight_kg: int):
        super().__init__(f"Invalid cargo weight: {cargo_weight_kg} kg. Cargo weight must be greater than 0.")

class NoTruckAvailable(Exception):
    def __init__(self, cargo_weight_kg: int):
        super().__init__(
            f"No truck available for capacity {cargo_weight_kg} kg. Please check the truck capacity and try again."
        )
