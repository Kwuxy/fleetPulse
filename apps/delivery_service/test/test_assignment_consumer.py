import asyncio
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.clients.kafka_client import QueueMessageStatus
from app.consumers import assignment_consumer
from app.exceptions import NotFoundException
from app.models.truck_assignment import TruckAssignmentCompleted, TruckAssignmentFailureReason
from app.services import delivery_service


def _get_success_assignment_completed_message():
    return {"delivery_id": "delivery-abc123", "truck_id": "truck-123", "assigned": True}


def _get_fail_assignment_completed_message():
    return {"delivery_id": "delivery-abc123", "truck_id": None, "assigned": False,
            "reason": TruckAssignmentFailureReason.INVALID_REQUEST, "description": "Invalid request", }


def _get_success_assignment_completed_parameters():
    return (
        _get_success_assignment_completed_message(),
        TruckAssignmentCompleted(delivery_id="delivery-abc123", truck_id="truck-123", assigned=True,
                                 reason=None, description=None, )
    )

def _get_fail_assignment_completed_parameters():
    return (
        _get_fail_assignment_completed_message(),
        TruckAssignmentCompleted(delivery_id="delivery-abc123", truck_id=None, assigned=False,
                                 reason=TruckAssignmentFailureReason.INVALID_REQUEST,
                                 description="Invalid request", )
    )


@pytest.mark.kafka
@pytest.mark.unit
class TestAssignmentConsumer:
    class TestBuildTruckAssignmentCompleted:

        @pytest.mark.parametrize("msg, expected_result", [
            _get_success_assignment_completed_parameters(),
            _get_fail_assignment_completed_parameters(),
        ], ids=["assigned", "denied"])
        def test_building_assignment_completed_success_on_valid_message(self, msg, expected_result):
            # - Arrange -
            # values passed in as parameters

            # - Act -
            result = assignment_consumer._build_truck_assignment_completed(msg)

            # - Assert Result -
            assert result == expected_result

        def test_building_assignment_completed_rejects_on_incomplete_message(self):
            # - Arrange -
            msg = {"delivery_id": "delivery-abc123"}  # missing required `assigned`

            # - Act & Assert -
            with pytest.raises(ValidationError):
                assignment_consumer._build_truck_assignment_completed(msg)

            # - Assert Result -
            # Exception raised, no assertions needed

    class TestHandleTruckAssignmentCompleted:
        @pytest.mark.parametrize("msg, expected_result", [
            _get_success_assignment_completed_parameters(),
            _get_fail_assignment_completed_parameters(),
        ], ids=["assigned", "denied"])
        def test_updates_delivery_and_returns_consumed_on_valid_message(self, monkeypatch, msg, expected_result):
            # - Arrange -
            mock_update_delivery_with_truck_assignment = AsyncMock()
            monkeypatch.setattr(delivery_service, "update_delivery_with_truck_assignment", mock_update_delivery_with_truck_assignment)

            # - Act -
            result = asyncio.run(assignment_consumer.handle_truck_assignment_completed(msg))

            # - Assert Result -
            assert result == QueueMessageStatus.CONSUMED

            # - Assert mock calls -
            mock_update_delivery_with_truck_assignment.assert_awaited_once_with(expected_result)

        def test_returns_consumed_without_raising_on_unknown_delivery(self, monkeypatch):
            # - Arrange -
            def raise_not_found(assignment):
                raise NotFoundException(assignment.delivery_id)

            mock_update_delivery_with_truck_assignment = AsyncMock(side_effect=raise_not_found)
            monkeypatch.setattr(delivery_service, "update_delivery_with_truck_assignment",
                                mock_update_delivery_with_truck_assignment)

            msg, assignment_completed = _get_success_assignment_completed_parameters()

            # - Act -
            result = asyncio.run(assignment_consumer.handle_truck_assignment_completed(msg))

            # - Assert Result -
            assert result == QueueMessageStatus.CONSUMED

            # - Assert mock calls -
            mock_update_delivery_with_truck_assignment.assert_awaited_once_with(assignment_completed)

        def test_returns_consumed_without_assigning_on_malformed_message(self, monkeypatch):
            # - Arrange -
            mock_update_delivery_with_truck_assignment = AsyncMock()
            monkeypatch.setattr(delivery_service, "update_delivery_with_truck_assignment",
                                mock_update_delivery_with_truck_assignment)

            msg = {"delivery_id": "delivery-abc123"}  # missing required `assigned`

            # - Act -
            result = asyncio.run(assignment_consumer.handle_truck_assignment_completed(msg))

            # - Assert Result -
            assert result == QueueMessageStatus.CONSUMED

            # - Assert mock calls -
            mock_update_delivery_with_truck_assignment.assert_not_awaited()
