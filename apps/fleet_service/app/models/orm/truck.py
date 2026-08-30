from sqlalchemy.orm import Mapped, mapped_column

from app.clients.db_client import Base
from app.models.truck import TruckStatus


class Truck(Base):
    __tablename__ = "trucks"

    id: Mapped[str] = mapped_column(primary_key=True)
    plate_number: Mapped[str]
    capacity_kg: Mapped[int]
    status: Mapped[TruckStatus] = mapped_column(default=TruckStatus.AVAILABLE)
