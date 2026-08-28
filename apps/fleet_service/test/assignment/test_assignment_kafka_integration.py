import asyncio
import json

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from app.clients import kafka_client
from app.consumers.assignment_consumer import handle_truck_assignment_requested
from app.models.truck import Truck, TruckStatus
from app.repositories import truck_repository


@pytest.fixture(autouse=True)
def clear_truck_repository():
    truck_repository.clear()


@pytest.mark.kafka
@pytest.mark.integration
@pytest.mark.asyncio
async def test_requested_message_round_trips_to_completed(kafka_bootstrap_servers, monkeypatch):
    monkeypatch.setattr(kafka_client, "KAFKA_BOOTSTRAP_SERVERS", kafka_bootstrap_servers)

    truck_repository.save_truck(
        Truck(id="truck-1", plate_number="AB-123-CD", capacity_kg=1000, status=TruckStatus.AVAILABLE)
    )

    await kafka_client.start_producer()
    await kafka_client.start_consuming(handle_truck_assignment_requested)

    result_consumer = AIOKafkaConsumer(
        "truck-assignment-completed",
        bootstrap_servers=kafka_bootstrap_servers,
        key_deserializer=lambda key: key.decode("utf-8") if key else None,
        value_deserializer=lambda value: json.loads(value) if value else None,
        auto_offset_reset="earliest",
    )
    await result_consumer.start()

    try:
        request_producer = AIOKafkaProducer(
            bootstrap_servers=kafka_bootstrap_servers,
            key_serializer=lambda key: key.encode("utf-8") if key else None,
            value_serializer=lambda value: json.dumps(value).encode("utf-8") if value else None,
        )
        await request_producer.start()
        try:
            await request_producer.send_and_wait(
                "truck-assignment-requested",
                key="delivery-1",
                value={"delivery_id": "delivery-1", "cargo_weight_kg": 500},
            )
        finally:
            await request_producer.stop()

        msg = await asyncio.wait_for(result_consumer.getone(), timeout=15)
    finally:
        await result_consumer.stop()
        await kafka_client.stop_consuming()
        await kafka_client.stop_producer()

    assert msg.key == "delivery-1"
    assert msg.value == {
        "delivery_id": "delivery-1",
        "truck_id": "truck-1",
        "assigned": True,
        "reason": None,
        "description": None,
    }
