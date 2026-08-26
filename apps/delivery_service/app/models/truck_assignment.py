from pydantic import BaseModel


class TruckAssignmentRequest(BaseModel):
    delivery_id: str
    cargo_weight_kg: int
    

class TruckAssignmentCompleted(BaseModel):
    delivery_id: str
    truck_id: str | None = None
    assigned: bool
