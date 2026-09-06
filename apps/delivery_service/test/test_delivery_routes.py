import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.main import app
from app.models.delivery import Delivery, DeliveryStatus, CreateDeliveryRequest
from app.services import delivery_service
from app.exceptions import InvalidClient, SameLocationsException, InvalidCargo, InvalidRequestedDate, NotFoundException

client = TestClient(app)


def _get_delivery(**overrides):
    default = {
        'id': 'delivery-1234',
        'client_id': 1,
        'pickup_location': "Brussels",
        'dropoff_location': "Paris",
        'cargo_weight_kg': 700,
        'requested_date': date.today() + timedelta(days=1),
        'status': DeliveryStatus.REQUESTED,
        'assigned_truck_id': None
    }
    default.update(overrides)
    return Delivery(**default)


@pytest.mark.routes
@pytest.mark.unit
class TestDeliveryRoutes:
    class TestCreateDeliveryEndpoint:
        @staticmethod
        def _get_valid_payload(**overrides):
            defaults = {
                "client_id": 1,
                "pickup_location": "Brussels",
                "dropoff_location": "Paris",
                "cargo_weight_kg": 700,
                "requested_date": str(date.today() + timedelta(days=1)),
            }
            defaults.update(overrides)
            return defaults

        def test_create_delivery_endpoint_returns_created_delivery(self, monkeypatch):
            # - Arrange -
            delivery = _get_delivery()
            mock_create_delivery = AsyncMock(return_value=delivery)
            monkeypatch.setattr(delivery_service, "create_delivery", mock_create_delivery)

            payload = self._get_valid_payload()
            request = CreateDeliveryRequest(**payload)

            # - Act -
            response = client.post("/deliveries", json=payload)

            # - Assert result -
            assert response.status_code == 201
            assert response.json() == delivery.model_dump(mode="json")

            # - Assert mock -
            mock_create_delivery.assert_awaited_once_with(request)

        @staticmethod
        def raise_invalid_client(req: CreateDeliveryRequest):
            raise InvalidClient(req.client_id)

        @staticmethod
        def raise_same_locations(req: CreateDeliveryRequest):
            raise SameLocationsException()

        @staticmethod
        def raise_invalid_cargo(req: CreateDeliveryRequest):
            raise InvalidCargo(req.cargo_weight_kg)

        @staticmethod
        def raise_invalid_requested_date(req: CreateDeliveryRequest):
            raise InvalidRequestedDate(req.requested_date)

        @pytest.mark.parametrize('side_effect_exception, payload', [
            (raise_invalid_client, _get_valid_payload()),
            (raise_same_locations, _get_valid_payload(pickup_location='Paris', dropoff_location='Paris')),
            (raise_invalid_cargo, _get_valid_payload(cargo_weight_kg=0)),
            (raise_invalid_requested_date, _get_valid_payload(requested_date=str(date.today() - timedelta(days=1)))),
        ])
        def test_create_deliveries_endpoint_rejects_exceptions(self, monkeypatch, side_effect_exception, payload):
            # - Arrange -
            mock_create_delivery = AsyncMock(side_effect=side_effect_exception)
            monkeypatch.setattr(delivery_service, "create_delivery", mock_create_delivery)

            request = CreateDeliveryRequest(**payload)

            # - Act -
            response = client.post("/deliveries", json=payload)

            # - Assert result -
            assert response.status_code == 400

            # - Assert mock -
            mock_create_delivery.assert_awaited_once_with(request)

    class TestListDeliveriesEndpoint:
        def test_list_deliveries_endpoint_returns_empty_list_when_no_deliveries_exist(self, monkeypatch):
            # - Arrange -
            mock_get_deliveries = AsyncMock(return_value=[])
            monkeypatch.setattr(delivery_service, "get_deliveries", mock_get_deliveries)

            # - Act -
            response = client.get("/deliveries")

            # - Assert result -
            assert response.status_code == 200
            assert response.json() == []

            # - Assert mock -
            mock_get_deliveries.assert_awaited_once()

        def test_list_deliveries_endpoint_returns_deliveries_from_service(self, monkeypatch):
            # - Arrange -
            deliveries = [
                _get_delivery(),
                _get_delivery(status=DeliveryStatus.ASSIGNED, assigned_truck_id='truck-4585')
            ]
            mock_get_deliveries = AsyncMock(return_value=deliveries)
            monkeypatch.setattr(delivery_service, "get_deliveries", mock_get_deliveries)

            # - Act -
            response = client.get("/deliveries")

            # - Assert result -
            assert response.status_code == 200
            assert response.json() == [delivery.model_dump(mode="json") for delivery in deliveries]

            # - Assert mock -
            mock_get_deliveries.assert_awaited_once()

    class TestGetDeliveryByIdEndpoint:
        def test_get_delivery_by_id_endpoint_returns_delivery(self, monkeypatch):
            # - Arrange -
            delivery = _get_delivery()
            mock_get_delivery_by_id = AsyncMock(return_value=delivery)
            monkeypatch.setattr(delivery_service, "get_delivery_by_id", mock_get_delivery_by_id)

            # - Act -
            response = client.get(f"/deliveries/{delivery.id}")

            # - Assert result -
            assert response.status_code == 200
            assert response.json() == delivery.model_dump(mode="json")

            # - Assert mock -
            mock_get_delivery_by_id.assert_awaited_once_with(delivery.id)

        def test_get_delivery_by_id_endpoint_returns_404_when_not_found(self, monkeypatch):
            # - Arrange -
            def raise_not_found(_delivery_id):
                raise NotFoundException(_delivery_id)

            mock_get_delivery_by_id = AsyncMock(side_effect=raise_not_found)
            monkeypatch.setattr(delivery_service, "get_delivery_by_id", mock_get_delivery_by_id)
            delivery_id = 'delivery-666'

            # - Act -
            response = client.get(f"/deliveries/{delivery_id}")

            # - Assert result -
            assert response.status_code == 404

            # - Assert mock -
            mock_get_delivery_by_id.assert_awaited_once_with(delivery_id)
