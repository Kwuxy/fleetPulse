from datetime import date

from sqlalchemy.orm import Mapped, mapped_column

from app.clients.db_client import Base
from app.models.delivery import DeliveryStatus, DeliveryDenialReason


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[str] = mapped_column(primary_key=True)
    client_id: Mapped[int]  # Could become a foreign key
    pickup_location: Mapped[str]
    dropoff_location: Mapped[str]
    cargo_weight_kg: Mapped[int]
    requested_date: Mapped[date]
    status: Mapped[DeliveryStatus] = mapped_column(default=DeliveryStatus.REQUESTED)
    assigned_truck_id: Mapped[str | None]
    denial_reason: Mapped[DeliveryDenialReason | None]
    denial_description: Mapped[str | None]