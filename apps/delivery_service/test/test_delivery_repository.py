from datetime import date, timedelta

import pytest
from models.delivery import Delivery, DeliveryStatus
from repositories import delivery_repository


@pytest.fixture(autouse=True)
def setup_and_teardown():
    delivery_repository.clear()


def test_save_delivery():
    deliveries = [
        Delivery(
            id='delivery-123',
            client_id=23,
            pickup_location="Test Location",
            dropoff_location="Test Destination",
            cargo_weight_kg=200,
            requested_date=(date.today() + timedelta(days=1)),
            status=DeliveryStatus.ASSIGNED,
            assigned_truck_id="truck-1234",),
        Delivery(
            id='delivery-456',
            client_id=23,
            pickup_location="Test Location",
            dropoff_location="Test Destination",
            cargo_weight_kg=600,
            requested_date=(date.today() + timedelta(days=1)),
            status=DeliveryStatus.REQUESTED,
            assigned_truck_id="truck-7894", ),
        ]

    for delivery in deliveries:
        delivery_repository.save(delivery)

    result = delivery_repository.get_deliveries()

    assert len(result) == len(deliveries)
    assert result == deliveries
