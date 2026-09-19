from datetime import datetime

from pydantic import BaseModel


class Coordinates(BaseModel):
    lat: float
    lon: float


class TruckDepartureScheduled(BaseModel):
    delivery_id: str
    truck_id: str
    pickup_location: Coordinates
    dropoff_location: Coordinates
    departure_time: datetime
