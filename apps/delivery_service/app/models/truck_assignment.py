from enum import Enum
from pydantic import BaseModel


class TruckAssignmentRequest(BaseModel):
    delivery_id: str
    cargo_weight_kg: int


class TruckAssignmentFailureReason(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    NO_AVAILABLE_TRUCK = "NO_AVAILABLE_TRUCK"


class TruckAssignmentCompleted(BaseModel):
    delivery_id: str
    truck_id: str | None = None
    assigned: bool
    reason: TruckAssignmentFailureReason | None = None
    description: str | None = None
