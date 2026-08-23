import json
import os

from aiokafka import AIOKafkaProducer

KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9094")

_producer: AIOKafkaProducer | None = None


async def start_producer() -> None:
    global _producer
    _producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        enable_idempotence=True,
        key_serializer=lambda key: key.encode("utf-8") if key else None,
        value_serializer=lambda value: json.dumps(value).encode("utf-8") if value else None,
    )
    await _producer.start()


async def stop_producer() -> None:
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None

def get_producer() -> AIOKafkaProducer:
    if _producer is None:
        raise RuntimeError("Producer is not started")
    return _producer

async def produce_truck_assignment_requested(delivery_id: str, cargo_weight_kg: int) -> None:
    await get_producer().send(
        'truck-assignment-requested',
        key=delivery_id,
        value={'delivery_id': delivery_id, 'cargo_weight_kg': cargo_weight_kg},
    )