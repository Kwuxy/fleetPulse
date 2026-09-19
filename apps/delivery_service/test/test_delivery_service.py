import asyncio
from datetime import timedelta, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from app.exceptions import InvalidCargo, InvalidRequestedDate, SameLocationsException, NotFoundException, \
    UnassignedTruckOnCompletedAssignment
from app.models.delivery import CreateDeliveryRequest, DeliveryStatus, Delivery
from app.models.truck_assignment import TruckAssignmentCompleted, TruckAssignmentFailureReason
from app.models.truck_departure import Coordinates
from app.producers import assignment_producer, departure_producer
from app.repositories import delivery_repository
from app.services import delivery_service
from app.clients import osrm_client


@pytest.mark.service
@pytest.mark.unit
class TestDeliveryService:
    @pytest.fixture()
    def mock_save_delivery(self, monkeypatch):
        mock = AsyncMock()
        monkeypatch.setattr(delivery_repository, "save_delivery", mock)
        return mock

    class TestCreateDelivery:
        @pytest.fixture(autouse=True)
        def mock_produce_truck_assignment_requested(self, monkeypatch):
            mock = AsyncMock()
            monkeypatch.setattr(assignment_producer, "produce_truck_assignment_requested", mock)
            return mock

        @staticmethod
        def _get_create_delivery_request(**overrides):
            defaults = dict(
                client_id=1,
                pickup_location="Brussels",
                dropoff_location="Paris",
                cargo_weight_kg=700,
                requested_datetime=datetime.today() + timedelta(days=1),
            )
            defaults.update(overrides)
            return CreateDeliveryRequest(**defaults)

        def test_create_delivery_succeeds_on_valid_data_and_produces_assignment_request(self,
                                                                                        mock_produce_truck_assignment_requested,
                                                                                        mock_save_delivery
                                                                                        ):
            # - Arrange -
            request = self._get_create_delivery_request()

            # - Act -
            delivery = asyncio.run(delivery_service.create_delivery(request))

            # - Assert Result -
            assert delivery.id.startswith("delivery-")
            assert delivery.client_id == 1
            assert delivery.pickup_location == "Brussels"
            assert delivery.dropoff_location == "Paris"
            assert delivery.cargo_weight_kg == 700
            assert delivery.status == DeliveryStatus.REQUESTED
            assert delivery.assigned_truck_id is None
            assert delivery.requested_datetime == request.requested_datetime
            assert delivery.denial_reason is None
            assert delivery.denial_description is None

            # - Assert mock calls -
            mock_save_delivery.assert_awaited_once_with(delivery)
            mock_produce_truck_assignment_requested.assert_awaited_once()
            sent_request = mock_produce_truck_assignment_requested.await_args.args[0]
            assert sent_request.delivery_id == delivery.id
            assert sent_request.cargo_weight_kg == 700

        def test_create_delivery_rejects_same_pickup_and_dropoff_locations(self,
                                                                           mock_produce_truck_assignment_requested,
                                                                           mock_save_delivery
                                                                           ):
            # - Arrange -
            request = self._get_create_delivery_request(pickup_location="Paris")

            # - Act -
            with pytest.raises(SameLocationsException):
                asyncio.run(delivery_service.create_delivery(request))

            # - Assert Result -
            # Exception raised, no assertions needed

            # - Assert mock calls -
            mock_save_delivery.assert_not_awaited()
            mock_produce_truck_assignment_requested.assert_not_awaited()

        def test_create_delivery_rejects_invalid_cargo_weight(self,
                                                              mock_produce_truck_assignment_requested,
                                                              mock_save_delivery
                                                              ):
            # - Arrange -
            request = self._get_create_delivery_request(cargo_weight_kg=0)

            # - Act -
            with pytest.raises(InvalidCargo):
                asyncio.run(delivery_service.create_delivery(request))

            # - Assert Result -
            # Exception raised, no assertions needed

            # - Assert mock calls -
            mock_save_delivery.assert_not_awaited()
            mock_produce_truck_assignment_requested.assert_not_awaited()

        def test_create_delivery_rejects_today_as_requested_datetime(self,
                                                                 mock_produce_truck_assignment_requested,
                                                                 mock_save_delivery
                                                                 ):
            # - Arrange -
            request = self._get_create_delivery_request(requested_datetime=datetime.today())

            # - Act -
            with pytest.raises(InvalidRequestedDate):
                asyncio.run(delivery_service.create_delivery(request))

            # - Assert Result -
            # Exception raised, no assertions needed

            # - Assert mock calls -
            mock_save_delivery.assert_not_awaited()
            mock_produce_truck_assignment_requested.assert_not_awaited()

    class TestUpdateDeliveryFromTruckAssignmentCompleted:
        @pytest.fixture(autouse=True)
        def mock_produce_truck_departure_scheduled(self, monkeypatch):
            mock = AsyncMock()
            monkeypatch.setattr(departure_producer, "produce_truck_departure_scheduled", mock)
            return mock

        @staticmethod
        def _get_create_truck_assignment_completed_success(**overrides):
            defaults = dict(
                delivery_id="delivery-1",
                truck_id="truck-123",
                assigned=True,
            )
            defaults.update(overrides)
            return TruckAssignmentCompleted(**defaults)

        @staticmethod
        def _get_create_truck_assignment_completed_failed(**overrides):
            defaults = dict(
                delivery_id="delivery-1",
                truck_id=None,
                assigned=False,
                reason=TruckAssignmentFailureReason.NO_AVAILABLE_TRUCK,
                description="No truck can carry 700 kg",
            )
            defaults.update(overrides)
            return TruckAssignmentCompleted(**defaults)

        def test_sets_status_assigned_and_truck_id_when_assigned(self, monkeypatch,
                                                                 mock_produce_truck_departure_scheduled,
                                                                 mock_save_delivery):
            # - Arrange -
            delivery = TestDeliveryService._get_initial_deliveries()[0]
            mock_get_deliveries_by_id = AsyncMock(return_value=delivery)
            monkeypatch.setattr(delivery_repository, "get_delivery_by_id", mock_get_deliveries_by_id)
            mock_get_city_coordinates = Mock(side_effect=[{'lat': 1.0, 'lon': 2.3}, {'lat': 10.7, 'lon': 20.5}])
            monkeypatch.setattr(osrm_client, "get_city_coordinates", mock_get_city_coordinates)
            mock_get_route_duration = AsyncMock(return_value=timedelta(minutes=20))
            monkeypatch.setattr(osrm_client, "get_route_duration", mock_get_route_duration)

            assignment = self._get_create_truck_assignment_completed_success()

            # - Act -
            asyncio.run(delivery_service.update_delivery_with_truck_assignment(assignment))

            # - Assert Result -
            assert delivery.status == DeliveryStatus.ASSIGNED
            assert delivery.assigned_truck_id == assignment.truck_id
            assert delivery.denial_reason is None
            assert delivery.denial_description is None

            # - Assert mock calls -
            mock_save_delivery.assert_awaited_once_with(delivery)
            mock_get_deliveries_by_id.assert_awaited_once_with(assignment.delivery_id)
            mock_produce_truck_departure_scheduled.assert_awaited_once()
            sent_request = mock_produce_truck_departure_scheduled.await_args.args[0]
            assert sent_request.delivery_id == delivery.id
            assert sent_request.truck_id == delivery.assigned_truck_id
            assert sent_request.pickup_location == Coordinates(lat=1.0, lon=2.3)
            assert sent_request.dropoff_location == Coordinates(lat=10.7, lon=20.5)
            assert sent_request.departure_time == delivery.requested_datetime - timedelta(minutes=20)

        @pytest.mark.parametrize("reason, description", [
            (TruckAssignmentFailureReason.INVALID_REQUEST, "Invalid request"),
            (TruckAssignmentFailureReason.NO_AVAILABLE_TRUCK, "No truck available"),
        ],
                                 )
        def test_sets_status_denied(self, monkeypatch,
                                    mock_produce_truck_departure_scheduled,
                                    mock_save_delivery,
                                    reason,
                                    description):
            # - Arrange -
            delivery = TestDeliveryService._get_initial_deliveries()[0]
            mock_get_deliveries_by_id = AsyncMock(return_value=delivery)
            monkeypatch.setattr(delivery_repository, "get_delivery_by_id", mock_get_deliveries_by_id)

            assignment = self._get_create_truck_assignment_completed_failed(reason=reason, description=description)

            # - Act -
            asyncio.run(delivery_service.update_delivery_with_truck_assignment(assignment))

            # - Assert Result -
            assert delivery.status == DeliveryStatus.DENIED
            assert delivery.assigned_truck_id is None
            assert delivery.denial_reason == reason
            assert delivery.denial_description == description

            # - Assert mock calls -
            mock_save_delivery.assert_awaited_once()
            mock_get_deliveries_by_id.assert_awaited_once_with(assignment.delivery_id)
            mock_produce_truck_departure_scheduled.assert_not_awaited()

        def test_raises_unassigned_truck_on_completed_assignment_for_no_assigned_truck(self, monkeypatch,
                                                                               mock_produce_truck_departure_scheduled,
                                                                               mock_save_delivery):
            # - Arrange -
            delivery = TestDeliveryService._get_initial_deliveries()[0]
            mock_get_deliveries_by_id = AsyncMock(return_value=delivery)
            monkeypatch.setattr(delivery_repository, "get_delivery_by_id", mock_get_deliveries_by_id)

            assignment = self._get_create_truck_assignment_completed_success(truck_id=None)

            # - Act -
            with pytest.raises(UnassignedTruckOnCompletedAssignment):
                asyncio.run(delivery_service.update_delivery_with_truck_assignment(assignment))

            # - Assert Result -
            # Exception raised, no assertions needed

            # - Assert mock calls -
            mock_save_delivery.assert_awaited_once()
            mock_get_deliveries_by_id.assert_awaited_once_with(assignment.delivery_id)
            mock_produce_truck_departure_scheduled.assert_not_awaited()

        def test_raises_not_found_for_unknown_delivery_id(self, monkeypatch,
                                                          mock_produce_truck_departure_scheduled,
                                                          mock_save_delivery):
            # - Arrange -
            mock_get_deliveries_by_id = AsyncMock(return_value=None)
            monkeypatch.setattr(delivery_repository, "get_delivery_by_id", mock_get_deliveries_by_id)

            assignment = self._get_create_truck_assignment_completed_success()

            # - Act -
            with pytest.raises(NotFoundException):
                asyncio.run(delivery_service.update_delivery_with_truck_assignment(assignment))

            # - Assert Result -
            # Exception raised, no assertions needed

            # - Assert mock calls -
            mock_save_delivery.assert_not_awaited()
            mock_get_deliveries_by_id.assert_awaited_once_with(assignment.delivery_id)
            mock_produce_truck_departure_scheduled.assert_not_awaited()

    class TestGetDeliveries:
        def test_get_deliveries_returns_deliveries_from_repository(self, monkeypatch):
            # - Arrange -
            initial_deliveries = TestDeliveryService._get_initial_deliveries()
            mock_get_deliveries = AsyncMock(return_value=initial_deliveries)
            monkeypatch.setattr(delivery_repository, "get_deliveries", mock_get_deliveries)

            # - Act -
            deliveries = asyncio.run(delivery_service.get_deliveries())

            # - Assert Result -
            assert deliveries == initial_deliveries

            # - Assert mock calls -
            mock_get_deliveries.assert_awaited_once()

        def test_get_delivery_by_id_returns_matching_delivery(self, monkeypatch):
            # - Arrange -
            initial_deliveries = TestDeliveryService._get_initial_deliveries()
            expected_delivery = initial_deliveries[1]
            mock_get_deliveries_by_id = AsyncMock(return_value=expected_delivery)
            monkeypatch.setattr(delivery_repository, "get_delivery_by_id", mock_get_deliveries_by_id)

            # - Act -
            delivery = asyncio.run(delivery_service.get_delivery_by_id(expected_delivery.id))

            # - Assert Result -
            assert delivery is not None
            assert delivery == expected_delivery

            # - Assert mock calls -
            mock_get_deliveries_by_id.assert_awaited_once()

        def test_get_delivery_by_id_raises_not_found_for_unknown_id(self, monkeypatch):
            # - Arrange -
            mock_get_deliveries_by_id = AsyncMock(return_value=None)
            monkeypatch.setattr(delivery_repository, "get_delivery_by_id", mock_get_deliveries_by_id)

            # - Act -
            with pytest.raises(NotFoundException):
                asyncio.run(delivery_service.get_delivery_by_id('fake-id'))

            # - Assert Result -
            # Exception raised, no assertions needed

            # - Assert mock calls -
            mock_get_deliveries_by_id.assert_awaited_once()

    @staticmethod
    def _get_delivery(**overrides):
        defaults = dict(
            id="delivery-1",
            client_id=1,
            pickup_location="Brussels",
            dropoff_location="Paris",
            cargo_weight_kg=700,
            requested_datetime=datetime.today() + timedelta(days=1),
            status=DeliveryStatus.REQUESTED,
            assigned_truck_id=None
        )
        defaults.update(overrides)
        return Delivery(**defaults)

    @staticmethod
    def _get_initial_deliveries():
        return [
            TestDeliveryService._get_delivery(),
            TestDeliveryService._get_delivery(id="delivery-2", pickup_location="Rome", cargo_weight_kg=1200),
        ]
