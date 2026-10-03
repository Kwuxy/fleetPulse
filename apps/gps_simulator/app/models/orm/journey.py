from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column, composite

from app.clients.db_client import Base


@dataclass
class CoordinatesORM:
    lat: float
    lon: float


class Journey(Base):
    __tablename__ = "journeys"

    delivery_id: Mapped[str] = mapped_column(primary_key=True)
    truck_id: Mapped[str] = mapped_column(index=True)
    pickup_location: Mapped[CoordinatesORM] = composite(mapped_column("pickup_lat"), mapped_column("pickup_lon"))
    dropoff_location: Mapped[CoordinatesORM] = composite(mapped_column("dropoff_lat"), mapped_column("dropoff_lon"))
    departure_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
