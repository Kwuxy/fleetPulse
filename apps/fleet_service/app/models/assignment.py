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

    @staticmethod
    def get_failed(delivery_id: str, reason: TruckAssignmentFailureReason, description: str | None = None) -> TruckAssignmentCompleted:
        return TruckAssignmentCompleted(delivery_id=delivery_id, truck_id=None, assigned=False, reason=reason, description=description)

    @staticmethod
    def get_success(delivery_id: str, truck_id: str) -> TruckAssignmentCompleted:
        return TruckAssignmentCompleted(delivery_id=delivery_id, truck_id=truck_id, assigned=True)
