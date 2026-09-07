import asyncio
from unittest.mock import AsyncMock, call

import pytest

from app.models.truck import Truck, TruckStatus
from app.services import assignment_service
from app.models.assignment import TruckAssignmentRequest, TruckAssignmentFailureReason
from app.exceptions import UnknownDelivery, InvalidCargoWeight, NoTruckAvailable
from app.clients import kafka_client
from app.consumers.assignment_consumer import handle_truck_assignment_requested


@pytest.mark.kafka
@pytest.mark.integration
@pytest.mark.asyncio
class TestAssignmentKafkaIntegration:
    async def test_requested_message_is_consumed_and_produces_completed_message_on_successful_assignment(self, monkeypatch, kafka_consumer, kafka_producer):
        # - Arrange -
        truck = Truck(id="truck-1", plate_number="AB-123-CD", capacity_kg=1000, status=TruckStatus.AVAILABLE)
        mock_assign_truck_to_delivery = AsyncMock(return_value=truck)
        monkeypatch.setattr(assignment_service, "assign_truck_to_delivery", mock_assign_truck_to_delivery)

        assignment_request = TruckAssignmentRequest(delivery_id="delivery-1", cargo_weight_kg=500)
        truck_assignment_requested_msg = {"delivery_id": assignment_request.delivery_id, "cargo_weight_kg": assignment_request.cargo_weight_kg}
        expected_truck_assignment_completed_msg = {
            "delivery_id": "delivery-1",
            "truck_id": "truck-1",
            "assigned": True,
            "reason": None,
            "description": None,
        }

        # - Act -
        await kafka_producer.send_and_wait(
            "truck-assignment-requested",
            key=assignment_request.delivery_id,
            value=truck_assignment_requested_msg,
        )

        # - Assert result -
        consumed_msg = await asyncio.wait_for(kafka_consumer.getone(), timeout=15)

        assert consumed_msg.key == assignment_request.delivery_id
        assert consumed_msg.value == expected_truck_assignment_completed_msg

        # - Assert mock -
        mock_assign_truck_to_delivery.assert_awaited_once_with(assignment_request)

    @staticmethod
    def raise_unknown_delivery(request):
        raise UnknownDelivery(request.delivery_id)

    @staticmethod
    def raise_invalid_cargo(request):
        raise InvalidCargoWeight(request.cargo_weight_kg)

    @staticmethod
    def raise_no_truck(request):
        raise NoTruckAvailable(request.cargo_weight_kg)

    @pytest.mark.parametrize("side_effect_exception, expected_reason", [
        (raise_unknown_delivery, TruckAssignmentFailureReason.INVALID_REQUEST),
        (raise_invalid_cargo, TruckAssignmentFailureReason.INVALID_REQUEST),
        (raise_no_truck, TruckAssignmentFailureReason.NO_AVAILABLE_TRUCK),
    ])
    async def test_requested_message_produces_denied_completed_message_on_invalid_request_error(self, monkeypatch, kafka_consumer, kafka_producer, side_effect_exception, expected_reason):
        # - Arrange -
        mock_assign_truck_to_delivery = AsyncMock(side_effect=side_effect_exception)
        monkeypatch.setattr(assignment_service, "assign_truck_to_delivery", mock_assign_truck_to_delivery)

        assignment_request = TruckAssignmentRequest(delivery_id="delivery-1", cargo_weight_kg=500)
        truck_assignment_requested_msg = {"delivery_id": assignment_request.delivery_id,
                                          "cargo_weight_kg": assignment_request.cargo_weight_kg}

        # - Act -
        await kafka_producer.send_and_wait(
            "truck-assignment-requested",
            key=assignment_request.delivery_id,
            value=truck_assignment_requested_msg,
        )

        # - Assert result -
        consumed_msg = await asyncio.wait_for(kafka_consumer.getone(), timeout=15)

        assert consumed_msg.key == assignment_request.delivery_id
        assert consumed_msg.value['truck_id'] is None
        assert consumed_msg.value['assigned'] == False
        assert consumed_msg.value['reason'] == expected_reason
        assert consumed_msg.value['description'] is not None and consumed_msg.value['description'] != ''

        # - Assert mock -
        mock_assign_truck_to_delivery.assert_awaited_once_with(assignment_request)

    async def test_message_is_redelivered_after_handler_raises_an_uncaught_exception(self, monkeypatch, kafka_consumer, kafka_producer):
        # - Arrange -
        truck = Truck(id="truck-1", plate_number="AB-123-CD", capacity_kg=1000, status=TruckStatus.AVAILABLE)
        mock_assign_truck_to_delivery = AsyncMock(side_effect=[RuntimeError("Mocked exception"), truck])
        monkeypatch.setattr(assignment_service, "assign_truck_to_delivery", mock_assign_truck_to_delivery)

        assignment_request = TruckAssignmentRequest(delivery_id="delivery-1", cargo_weight_kg=500)
        truck_assignment_requested_msg = {"delivery_id": assignment_request.delivery_id,
                                          "cargo_weight_kg": assignment_request.cargo_weight_kg}
        expected_truck_assignment_completed_msg = {
            "delivery_id": "delivery-1",
            "truck_id": "truck-1",
            "assigned": True,
            "reason": None,
            "description": None,
        }

        # - Act -
        await kafka_producer.send_and_wait(
            "truck-assignment-requested",
            key=assignment_request.delivery_id,
            value=truck_assignment_requested_msg,
        )

        await asyncio.wait_for(_wait_for_await_count(mock_assign_truck_to_delivery, 1), timeout=15)

        # Manually "restart" the consuming loop to simulate a restart of the consumer
        await kafka_client.stop_consuming()
        await kafka_client.start_consuming(handle_truck_assignment_requested)

        # - Assert result -
        consumed_msg = await asyncio.wait_for(kafka_consumer.getone(), timeout=15)

        assert consumed_msg.key == assignment_request.delivery_id
        assert consumed_msg.value == expected_truck_assignment_completed_msg

        # - Assert mock -
        assert mock_assign_truck_to_delivery.await_count == 2
        mock_assign_truck_to_delivery.assert_has_awaits([call(assignment_request), call(assignment_request)])

    async def test_offset_is_committed_after_successful_handling_so_message_is_not_redelivered(self, monkeypatch, kafka_consumer, kafka_producer):
        # - Arrange -
        truck = Truck(id="truck-1", plate_number="AB-123-CD", capacity_kg=1000, status=TruckStatus.AVAILABLE)
        mock_assign_truck_to_delivery = AsyncMock(return_value=truck)
        monkeypatch.setattr(assignment_service, "assign_truck_to_delivery", mock_assign_truck_to_delivery)

        assignment_request = TruckAssignmentRequest(delivery_id="delivery-1", cargo_weight_kg=500)
        truck_assignment_requested_msg = {"delivery_id": assignment_request.delivery_id,
                                          "cargo_weight_kg": assignment_request.cargo_weight_kg}

        # - Act -
        await kafka_producer.send_and_wait(
            "truck-assignment-requested",
            key=assignment_request.delivery_id,
            value=truck_assignment_requested_msg,
        )

        await asyncio.wait_for(kafka_consumer.getone(), timeout=15)
        await asyncio.sleep(0.5)  # Waiting for the message to be committed, avoid race condition

        # Manually "restart" the consuming loop to simulate a restart of the consumer
        await kafka_client.stop_consuming()
        await kafka_client.start_consuming(handle_truck_assignment_requested)

        await asyncio.sleep(1)  # Giving time to kafka to redeliver the message

        # - Assert result -
        # The message should not be redelivered - No assertion needed

        # - Assert mock -
        mock_assign_truck_to_delivery.assert_awaited_once_with(assignment_request)

    async def test_malformed_request_message_is_dropped_without_producing_a_completed_message(self, monkeypatch, kafka_consumer, kafka_producer):
        # - Arrange -
        truck = Truck(id="truck-1", plate_number="AB-123-CD", capacity_kg=1000, status=TruckStatus.AVAILABLE)
        mock_assign_truck_to_delivery = AsyncMock(return_value=truck)
        monkeypatch.setattr(assignment_service, "assign_truck_to_delivery", mock_assign_truck_to_delivery)

        assignment_request = TruckAssignmentRequest(delivery_id="delivery-1", cargo_weight_kg=500)
        truck_assignment_requested_msg = {"delivery_id": assignment_request.delivery_id}  # Missing required `cargo_weight_kg`

        # - Act -
        await kafka_producer.send_and_wait(
            "truck-assignment-requested",
            key=assignment_request.delivery_id,
            value=truck_assignment_requested_msg,
        )

        await asyncio.sleep(1)  # give the consumer a chance to fetch and process a message if any

        # - Assert result -
        # No message consumed, no assertions needed

        # - Assert mock -
        mock_assign_truck_to_delivery.assert_not_awaited()


async def _wait_for_await_count(mock, count):
    while mock.await_count < count:
        await asyncio.sleep(0.1)
