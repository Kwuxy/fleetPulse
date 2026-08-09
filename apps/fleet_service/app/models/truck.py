from pydantic import BaseModel
from enum import Enum

class TruckStatus(str, Enum):
    AVAILABLE = "available"
    IN_USE = "in_use"
    IN_REPAIR = "in_repair"

class CreateTruckRequest(BaseModel):
    plate_number: str
    capacity_kg: int

class Truck(BaseModel):
    id: str
    plate_number: str
    capacity_kg: int
    status: TruckStatus = TruckStatus.AVAILABLE
