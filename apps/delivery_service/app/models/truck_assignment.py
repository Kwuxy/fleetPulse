from pydantic import BaseModel


class TruckAssignmentCompleted(BaseModel):
    delivery_id: str
    truck_id: str | None = None
    assigned: bool
