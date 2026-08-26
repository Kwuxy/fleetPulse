from datetime import date
from enum import Enum
from pydantic import BaseModel


class DeliveryStatus(str, Enum):
    REQUESTED = "requested"
    ASSIGNED = "assigned"
    DENIED = "denied"
    COMPLETED = "completed"


class DeliveryDenialReason(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    NO_AVAILABLE_TRUCK = "NO_AVAILABLE_TRUCK"


class Delivery(BaseModel):
    id: str
    client_id: int
    pickup_location: str
    dropoff_location: str
    cargo_weight_kg: int
    requested_date: date
    status: DeliveryStatus
    assigned_truck_id: str | None
    denial_reason: DeliveryDenialReason | None = None
    denial_description: str | None = None

class CreateDeliveryRequest(BaseModel):
    client_id: int
    pickup_location: str
    dropoff_location: str
    cargo_weight_kg: int
    requested_date: date
