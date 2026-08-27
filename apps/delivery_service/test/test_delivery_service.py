import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from app.exceptions import InvalidCargo, InvalidRequestedDate, SameLocationsException, NotFoundException
from app.models.delivery import CreateDeliveryRequest, DeliveryStatus, DeliveryDenialReason
from app.models.truck_assignment import TruckAssignmentCompleted, TruckAssignmentFailureReason
from app.producers import assignment_producer
from app.repositories import delivery_repository
from app.services import delivery_service


@pytest.fixture(autouse=True)
def clear_repository():
    delivery_repository.clear()


@pytest.fixture(autouse=True)
def mock_produce_truck_assignment_requested(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(assignment_producer, "produce_truck_assignment_requested", mock)
    return mock


def _valid_request(**overrides):
    defaults = dict(
        client_id=1,
        pickup_location="Brussels",
        dropoff_location="Paris",
        cargo_weight_kg=700,
        requested_date=date.today() + timedelta(days=1),
    )
    defaults.update(overrides)
    return CreateDeliveryRequest(**defaults)


@pytest.mark.service
@pytest.mark.unit
class TestCreateDelivery:
    def test_create_delivery_saves_delivery_as_requested_and_produces_assignment_request(
        self, mock_produce_truck_assignment_requested
    ):
        request = _valid_request()

        delivery = asyncio.run(delivery_service.create_delivery(request))

        assert delivery.id.startswith("delivery-")
        assert delivery.client_id == 1
        assert delivery.pickup_location == "Brussels"
        assert delivery.dropoff_location == "Paris"
        assert delivery.cargo_weight_kg == 700
        assert delivery.status == DeliveryStatus.REQUESTED
        assert delivery.assigned_truck_id is None
        assert delivery_repository.get_delivery_by_id(delivery.id) == delivery

        mock_produce_truck_assignment_requested.assert_awaited_once()
        sent_request = mock_produce_truck_assignment_requested.await_args.args[0]
        assert sent_request.delivery_id == delivery.id
        assert sent_request.cargo_weight_kg == 700

    def test_create_delivery_rejects_same_pickup_and_dropoff_locations(self):
        request = _valid_request(dropoff_location="Brussels")

        with pytest.raises(SameLocationsException):
            asyncio.run(delivery_service.create_delivery(request))

    def test_create_delivery_rejects_invalid_cargo_weight(self):
        request = _valid_request(cargo_weight_kg=0)

        with pytest.raises(InvalidCargo):
            asyncio.run(delivery_service.create_delivery(request))

    def test_create_delivery_rejects_today_as_requested_date(self):
        request = _valid_request(requested_date=date.today())

        with pytest.raises(InvalidRequestedDate):
            asyncio.run(delivery_service.create_delivery(request))


@pytest.mark.service
@pytest.mark.unit
class TestGetDeliveries:
    def test_get_deliveries_returns_created_deliveries(self):
        requests = [
            _valid_request(),
            _valid_request(client_id=3, pickup_location="Rome", dropoff_location="Berlin", cargo_weight_kg=900),
        ]

        deliveries = [asyncio.run(delivery_service.create_delivery(request)) for request in requests]
        result = delivery_service.get_deliveries()

        assert len(result) == 2
        assert result == deliveries

    def test_get_deliveries_by_id_returns_created_deliveries(self):
        requests = [
            _valid_request(),
            _valid_request(client_id=3, pickup_location="Rome", dropoff_location="Berlin", cargo_weight_kg=900),
        ]

        deliveries = [asyncio.run(delivery_service.create_delivery(request)) for request in requests]
        result = delivery_service.get_delivery_by_id(deliveries[0].id)
        assert result == deliveries[0]

    def test_get_deliveries_by_id_with_wrong_id_raises_exception(self):
        asyncio.run(delivery_service.create_delivery(_valid_request()))

        with pytest.raises(NotFoundException):
            delivery_service.get_delivery_by_id('fake_id')


@pytest.mark.service
@pytest.mark.unit
class TestUpdateDeliveryWithTruckAssignment:
    def test_sets_status_assigned_and_truck_id_when_assigned(self):
        delivery = asyncio.run(delivery_service.create_delivery(_valid_request()))
        assignment = TruckAssignmentCompleted(delivery_id=delivery.id, truck_id="truck-123", assigned=True)

        delivery_service.update_delivery_with_truck_assignment(assignment)

        updated = delivery_service.get_delivery_by_id(delivery.id)
        assert updated.status == DeliveryStatus.ASSIGNED
        assert updated.assigned_truck_id == "truck-123"
        assert updated.denial_reason is None
        assert updated.denial_description is None

    def test_sets_status_denied_with_reason_and_description_when_not_assigned(self):
        delivery = asyncio.run(delivery_service.create_delivery(_valid_request()))
        assignment = TruckAssignmentCompleted(
            delivery_id=delivery.id,
            assigned=False,
            reason=TruckAssignmentFailureReason.NO_AVAILABLE_TRUCK,
            description="No truck can carry 700 kg",
        )

        delivery_service.update_delivery_with_truck_assignment(assignment)

        updated = delivery_service.get_delivery_by_id(delivery.id)
        assert updated.status == DeliveryStatus.DENIED
        assert updated.assigned_truck_id is None
        assert updated.denial_reason == DeliveryDenialReason.NO_AVAILABLE_TRUCK
        assert updated.denial_description == "No truck can carry 700 kg"

    def test_raises_not_found_for_unknown_delivery_id(self):
        assignment = TruckAssignmentCompleted(delivery_id="fake_id", truck_id="truck-123", assigned=True)

        with pytest.raises(NotFoundException):
            delivery_service.update_delivery_with_truck_assignment(assignment)
