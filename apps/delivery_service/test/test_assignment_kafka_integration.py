import asyncio
import json
from datetime import date, timedelta

import pytest
from aiokafka import AIOKafkaProducer

from app.clients import kafka_client
from app.consumers.assignment_consumer import handle_truck_assignment_completed
from app.models.delivery import Delivery, DeliveryStatus
from app.repositories import delivery_repository


@pytest.fixture(autouse=True)
async def clear_delivery_repository():
    await delivery_repository.clear()


@pytest.mark.kafka
@pytest.mark.integration
@pytest.mark.asyncio
async def test_completed_message_updates_delivery_status(kafka_bootstrap_servers, monkeypatch):
    monkeypatch.setattr(kafka_client, "KAFKA_BOOTSTRAP_SERVERS", kafka_bootstrap_servers)

    delivery_repository.save(
        Delivery(
            id="delivery-1",
            client_id=1,
            pickup_location="Warehouse A",
            dropoff_location="Warehouse B",
            cargo_weight_kg=500,
            requested_date=date.today() + timedelta(days=1),
            status=DeliveryStatus.REQUESTED,
            assigned_truck_id=None,
        )
    )

    await kafka_client.start_producer()
    await kafka_client.start_consuming(handle_truck_assignment_completed)

    try:
        request_producer = AIOKafkaProducer(
            bootstrap_servers=kafka_bootstrap_servers,
            key_serializer=lambda key: key.encode("utf-8") if key else None,
            value_serializer=lambda value: json.dumps(value).encode("utf-8") if value else None,
        )
        await request_producer.start()
        try:
            await request_producer.send_and_wait(
                "truck-assignment-completed",
                key="delivery-1",
                value={
                    "delivery_id": "delivery-1",
                    "truck_id": "truck-1",
                    "assigned": True,
                    "reason": None,
                    "description": None,
                },
            )
        finally:
            await request_producer.stop()

        delivery = await asyncio.wait_for(_wait_until_no_longer_requested("delivery-1"), timeout=15)
    finally:
        await kafka_client.stop_consuming()
        await kafka_client.stop_producer()

    assert delivery.status == DeliveryStatus.ASSIGNED
    assert delivery.assigned_truck_id == "truck-1"


async def _wait_until_no_longer_requested(delivery_id: str) -> Delivery:
    while True:
        delivery = delivery_repository.get_delivery_by_id(delivery_id)
        if delivery.status != DeliveryStatus.REQUESTED:
            return delivery
        await asyncio.sleep(0.1)
