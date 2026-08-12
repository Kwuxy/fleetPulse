import asyncio
from datetime import date, timedelta
import pytest

from app.exceptions import InvalidCargo, InvalidRequestedDate, SameLocationsException, NotFoundException
from app.models.delivery import CreateDeliveryRequest, DeliveryStatus
from app.repositories import delivery_repository
from app.clients import fleet_client
from app.services import delivery_service


@pytest.fixture(autouse=True)
def clear_repository():
    delivery_repository.clear()


@pytest.mark.service
@pytest.mark.unit
class TestDeliveryService:
    def test_create_delivery_assigns_truck_when_fleet_returns_truck_id(self, monkeypatch):
        async def fake_assign_truck_to_delivery(delivery_id: str, cargo_weight_kg: int) -> str:
            return "truck-123"

        monkeypatch.setattr(
            fleet_client,
            "assign_truck_to_delivery",
            fake_assign_truck_to_delivery,
        )

        request = CreateDeliveryRequest(
            client_id=1,
            pickup_location="Brussels",
            dropoff_location="Paris",
            cargo_weight_kg=700,
            requested_date=date.today() + timedelta(days=1),
        )

        delivery = asyncio.run(delivery_service.create_delivery(request))

        assert delivery.id.startswith("delivery-")
        assert delivery.client_id == 1
        assert delivery.pickup_location == "Brussels"
        assert delivery.dropoff_location == "Paris"
        assert delivery.cargo_weight_kg == 700
        assert delivery.status == DeliveryStatus.ASSIGNED
        assert delivery.assigned_truck_id == "truck-123"

    def test_create_delivery_denies_delivery_when_fleet_returns_no_truck(self, monkeypatch):
        async def fake_assign_truck_to_delivery(delivery_id: str, cargo_weight_kg: int) -> None:
            return None

        monkeypatch.setattr(
            fleet_client,
            "assign_truck_to_delivery",
            fake_assign_truck_to_delivery,
        )

        request = CreateDeliveryRequest(
            client_id=1,
            pickup_location="Brussels",
            dropoff_location="Paris",
            cargo_weight_kg=700,
            requested_date=date.today() + timedelta(days=1),
        )

        delivery = asyncio.run(delivery_service.create_delivery(request))

        assert delivery.id.startswith("delivery-")
        assert delivery.status == DeliveryStatus.DENIED
        assert delivery.assigned_truck_id is None

    def test_create_delivery_rejects_same_pickup_and_dropoff_locations(self, monkeypatch):
        async def fake_assign_truck_to_delivery(delivery_id: str, cargo_weight_kg: int) -> str:
            return "truck-123"

        monkeypatch.setattr(
            fleet_client,
            "assign_truck_to_delivery",
            fake_assign_truck_to_delivery,
        )

        request = CreateDeliveryRequest(
            client_id=1,
            pickup_location="Brussels",
            dropoff_location="Brussels",
            cargo_weight_kg=700,
            requested_date=date.today() + timedelta(days=1),
        )

        with pytest.raises(SameLocationsException):
            asyncio.run(delivery_service.create_delivery(request))

    def test_create_delivery_rejects_invalid_cargo_weight(self, monkeypatch):
        async def fake_assign_truck_to_delivery(delivery_id: str, cargo_weight_kg: int) -> str:
            return "truck-123"

        monkeypatch.setattr(
            fleet_client,
            "assign_truck_to_delivery",
            fake_assign_truck_to_delivery,
        )

        request = CreateDeliveryRequest(
            client_id=1,
            pickup_location="Brussels",
            dropoff_location="Paris",
            cargo_weight_kg=0,
            requested_date=date.today() + timedelta(days=1),
        )

        with pytest.raises(InvalidCargo):
            asyncio.run(delivery_service.create_delivery(request))

    def test_create_delivery_rejects_today_as_requested_date(self, monkeypatch):
        async def fake_assign_truck_to_delivery(delivery_id: str, cargo_weight_kg: int) -> str:
            return "truck-123"

        monkeypatch.setattr(
            fleet_client,
            "assign_truck_to_delivery",
            fake_assign_truck_to_delivery,
        )

        request = CreateDeliveryRequest(
            client_id=1,
            pickup_location="Brussels",
            dropoff_location="Paris",
            cargo_weight_kg=700,
            requested_date=date.today(),
        )

        with pytest.raises(InvalidRequestedDate):
            asyncio.run(delivery_service.create_delivery(request))

    def test_get_deliveries_returns_created_deliveries(self, monkeypatch):
        async def fake_assign_truck_to_delivery(delivery_id: str, cargo_weight_kg: int) -> str:
            return "truck-123"

        monkeypatch.setattr(
            fleet_client,
            "assign_truck_to_delivery",
            fake_assign_truck_to_delivery,
        )

        requests = [
            CreateDeliveryRequest(
                client_id=1,
                pickup_location="Brussels",
                dropoff_location="Paris",
                cargo_weight_kg=700,
                requested_date=date.today() + timedelta(days=1),
            ),
            CreateDeliveryRequest(
                client_id=3,
                pickup_location="Rome",
                dropoff_location="Berlin",
                cargo_weight_kg=900,
                requested_date=date.today() + timedelta(days=1),
            )
        ]

        deliveries = [asyncio.run(delivery_service.create_delivery(request)) for request in requests]
        result = delivery_service.get_deliveries()

        assert len(result) == 2
        assert result == deliveries

    def test_get_deliveries_by_id_returns_created_deliveries(self, monkeypatch):
        async def fake_assign_truck_to_delivery(delivery_id: str, cargo_weight_kg: int) -> str:
            return "truck-123"

        monkeypatch.setattr(
            fleet_client,
            "assign_truck_to_delivery",
            fake_assign_truck_to_delivery,
        )

        requests = [
            CreateDeliveryRequest(
                client_id=1,
                pickup_location="Brussels",
                dropoff_location="Paris",
                cargo_weight_kg=700,
                requested_date=date.today() + timedelta(days=1),
            ),
            CreateDeliveryRequest(
                client_id=3,
                pickup_location="Rome",
                dropoff_location="Berlin",
                cargo_weight_kg=900,
                requested_date=date.today() + timedelta(days=1),
            )
        ]

        deliveries = [asyncio.run(delivery_service.create_delivery(request)) for request in requests]
        result = delivery_service.get_delivery_by_id(deliveries[0].id)
        assert result == deliveries[0]

    def test_get_deliveries_by_id_with_wrong_id_raises_exception(self, monkeypatch):
        async def fake_assign_truck_to_delivery(delivery_id: str, cargo_weight_kg: int) -> str:
            return "truck-123"

        monkeypatch.setattr(
            fleet_client,
            "assign_truck_to_delivery",
            fake_assign_truck_to_delivery,
        )

        requests = [
            CreateDeliveryRequest(
                client_id=1,
                pickup_location="Brussels",
                dropoff_location="Paris",
                cargo_weight_kg=700,
                requested_date=date.today() + timedelta(days=1),
            ),
            CreateDeliveryRequest(
                client_id=3,
                pickup_location="Rome",
                dropoff_location="Berlin",
                cargo_weight_kg=900,
                requested_date=date.today() + timedelta(days=1),
            )
        ]

        deliveries = [asyncio.run(delivery_service.create_delivery(request)) for request in requests]
        with pytest.raises(NotFoundException):
            delivery_service.get_delivery_by_id('fake_id')
