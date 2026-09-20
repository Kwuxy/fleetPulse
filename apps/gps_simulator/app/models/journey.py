from datetime import datetime
from pydantic import BaseModel

from app.models.truck_departure import Coordinates


class Journey(BaseModel):
    delivery_id: str
    truck_id: str
    pickup_location: Coordinates
    dropoff_location: Coordinates
    departure_time: datetime
