import asyncio
from typing import Literal
from unittest.mock import AsyncMock, call

import pytest

from app.models.truck_assignment import TruckAssignmentCompleted, TruckAssignmentFailureReason
from app.services import delivery_service
from app.clients import kafka_client
from app.consumers.assignment_consumer import handle_truck_assignment_completed
from app.exceptions import NotFoundException


def _get_success_truck_assignment_completed(**overrides):
    defaults = {
        "delivery_id": "delivery-1",
        "truck_id": "truck-1",
        "assigned": True,
        "reason": None,
        "description": None,
    }
    defaults.update(overrides)
    return TruckAssignmentCompleted(**defaults)


def _get_failed_truck_assignment_completed(**overrides):
    defaults = {
        "delivery_id": "delivery-1",
        "truck_id": None,
        "assigned": False,
        "reason": TruckAssignmentFailureReason.NO_AVAILABLE_TRUCK,
        "description": "No trucks available",
    }
    defaults.update(overrides)
    return TruckAssignmentCompleted(**defaults)


def _get_truck_assignment_completed_parameters(assignment_type: Literal["success", "failed"]):
    truck_assignment_completed = _get_success_truck_assignment_completed() if assignment_type == "success" else _get_failed_truck_assignment_completed()
    truck_assignment_completed_msg = truck_assignment_completed.model_dump()
    return truck_assignment_completed, truck_assignment_completed_msg


@pytest.mark.kafka
@pytest.mark.integration
@pytest.mark.asyncio
class TestDeliveryKafkaIntegration:
    @pytest.mark.parametrize("assignment_type", ["success", "failed"])
    async def test_completed_message_updates_delivery_via_service(self, monkeypatch, kafka_consumer, kafka_producer,
                                                                  assignment_type: Literal["success", "failed"]):
        # - Arrange -
        mock_update_delivery_with_truck_assignment = AsyncMock()
        monkeypatch.setattr(delivery_service, "update_delivery_with_truck_assignment",
                            mock_update_delivery_with_truck_assignment)
        assignment_request, truck_assignment_requested_msg = _get_truck_assignment_completed_parameters(assignment_type)

        # - Act -
        await kafka_producer.send_and_wait(
            "truck-assignment-completed",
            key=assignment_request.delivery_id,
            value=truck_assignment_requested_msg,
        )

        await asyncio.wait_for(_wait_for_await_count(mock_update_delivery_with_truck_assignment, 1), timeout=15)

        # - Assert result -
        # No message consumed, no assertions needed

        # - Assert mock -
        mock_update_delivery_with_truck_assignment.assert_awaited_once_with(assignment_request)

    async def test_returns_consumed_without_raising_when_delivery_is_unknown(self, monkeypatch, kafka_consumer,
                                                                             kafka_producer):
        # - Arrange -
        def raise_not_found(delivery_id):
            raise NotFoundException(delivery_id)

        mock_update_delivery_with_truck_assignment = AsyncMock(side_effect=raise_not_found)
        monkeypatch.setattr(delivery_service, "update_delivery_with_truck_assignment",
                            mock_update_delivery_with_truck_assignment)
        assignment_request, truck_assignment_requested_msg = _get_truck_assignment_completed_parameters('success')

        # - Act -
        await kafka_producer.send_and_wait(
            "truck-assignment-completed",
            key=assignment_request.delivery_id,
            value=truck_assignment_requested_msg,
        )

        await asyncio.wait_for(_wait_for_await_count(mock_update_delivery_with_truck_assignment, 1), timeout=15)

        # - Assert result -
        # No message consumed, no assertions needed

        # - Assert mock -
        mock_update_delivery_with_truck_assignment.assert_awaited_once_with(assignment_request)

    async def test_message_is_redelivered_after_handler_raises_an_uncaught_exception(self, monkeypatch, kafka_consumer,
                                                                                     kafka_producer):
        # - Arrange -
        mock_update_delivery_with_truck_assignment = AsyncMock(side_effect=[RuntimeError("Mocked exception"), None])
        monkeypatch.setattr(delivery_service, "update_delivery_with_truck_assignment",
                            mock_update_delivery_with_truck_assignment)
        assignment_request, truck_assignment_requested_msg = _get_truck_assignment_completed_parameters("success")

        # - Act -
        await kafka_producer.send_and_wait(
            "truck-assignment-completed",
            key=assignment_request.delivery_id,
            value=truck_assignment_requested_msg,
        )

        await asyncio.wait_for(_wait_for_await_count(mock_update_delivery_with_truck_assignment, 1), timeout=15)
        await restart_kafka_client()
        await asyncio.wait_for(_wait_for_await_count(mock_update_delivery_with_truck_assignment, 2), timeout=15)

        # - Assert result -
        # No message consumed, no assertions needed

        # - Assert mock -
        assert mock_update_delivery_with_truck_assignment.await_count == 2
        mock_update_delivery_with_truck_assignment.assert_has_awaits(
            [call(assignment_request), call(assignment_request)])

    async def test_offset_is_committed_after_successful_handling_so_message_is_not_redelivered(self, monkeypatch,
                                                                                               kafka_consumer,
                                                                                               kafka_producer):
        # - Arrange -
        mock_update_delivery_with_truck_assignment = AsyncMock()
        monkeypatch.setattr(delivery_service, "update_delivery_with_truck_assignment",
                            mock_update_delivery_with_truck_assignment)
        assignment_request, truck_assignment_requested_msg = _get_truck_assignment_completed_parameters("success")

        # - Act -
        await kafka_producer.send_and_wait(
            "truck-assignment-completed",
            key=assignment_request.delivery_id,
            value=truck_assignment_requested_msg,
        )

        await asyncio.wait_for(_wait_for_await_count(mock_update_delivery_with_truck_assignment, 1), timeout=15)
        await asyncio.sleep(0.5)  # Waiting for the message to be committed, avoid race condition

        await restart_kafka_client()
        await asyncio.sleep(1)  # Giving time to kafka to redeliver the message

        # - Assert result -
        # No message consumed, no assertions needed

        # - Assert mock -
        mock_update_delivery_with_truck_assignment.assert_awaited_once_with(assignment_request)

    async def test_malformed_completed_message_is_dropped_without_updating_delivery(self, monkeypatch, kafka_consumer,
                                                                                    kafka_producer):
        # - Arrange -
        mock_update_delivery_with_truck_assignment = AsyncMock()
        monkeypatch.setattr(delivery_service, "update_delivery_with_truck_assignment",
                            mock_update_delivery_with_truck_assignment)
        _, truck_assignment_requested_msg = _get_truck_assignment_completed_parameters('success')
        del truck_assignment_requested_msg['assigned']  # Missing required `assigned`

        # - Act -
        await kafka_producer.send_and_wait(
            "truck-assignment-completed",
            key=truck_assignment_requested_msg['delivery_id'],
            value=truck_assignment_requested_msg,
        )

        await asyncio.sleep(1)  # give the consumer a chance to fetch and process a message if any

        # - Assert result -
        # No message consumed, no assertions needed

        # - Assert mock -
        mock_update_delivery_with_truck_assignment.assert_not_awaited()


async def _wait_for_await_count(mock, count):
    while mock.await_count < count:
        await asyncio.sleep(0.1)


async def restart_kafka_client():
    # Manually "restart" the consuming loop to simulate a restart of the consumer
    await kafka_client.stop_consuming()
    await kafka_client.start_consuming(handle_truck_assignment_completed)
