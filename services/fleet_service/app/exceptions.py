class InvalidTruckCapacity(Exception):
    def __init__(self, capacity: int):
        super().__init__(f"Invalid truck capacity: {capacity} kg")

class InvalidPlateNumber(Exception):
    def __init__(self, plate_number: str):
        super().__init__(f"Invalid plate number: {plate_number}")

class DuplicatePlateNumber(Exception):
    def __init__(self, plate_number: str):
        super().__init__(f"Plate number already exists: {plate_number}")
