from enum import Enum

from pydantic import BaseModel


class TruckAssignmentRequest(BaseModel):
    delivery_id: str
    cargo_weight_kg: int

class TruckAssignmentFailureReason(str, Enum):
    NO_AVAILABLE_TRUCK = "NO_AVAILABLE_TRUCK"

class TruckAssignmentResponse(BaseModel):
    truck_id: str | None = None
    assigned: bool
    reason: TruckAssignmentFailureReason | None = None
