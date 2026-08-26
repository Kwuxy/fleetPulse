import asyncio
import json
import logging
import os
from enum import Enum, auto
from typing import Callable

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9094")


# =============== Consumer ===============
_consumer: AIOKafkaConsumer | None = None
_consume_task: asyncio.Task | None = None


def get_consumer() -> AIOKafkaConsumer:
    if _consumer is None:
        raise RuntimeError("Consumer is not started")
    return _consumer


def get_consume_task() -> asyncio.Task:
    if _consume_task is None:
        raise RuntimeError("Consume task is not started")
    return _consume_task


async def start_consuming(handler: Callable) -> None:
    global _consumer, _consume_task
    if _consumer is not None:
        raise RuntimeError("Consumer is already started")

    _consumer = AIOKafkaConsumer(
        'truck-assignment-completed',
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        key_deserializer=lambda key: key.decode("utf-8") if key else None,
        value_deserializer=lambda value: json.loads(value) if value else None,
        group_id='delivery-service-group',
        enable_auto_commit=False,
    )
    await _consumer.start()

    if _consume_task is not None:
        raise RuntimeError("Consume task is already started")

    _consume_task = asyncio.create_task(_run(handler))


async def _run(handler: Callable) -> None:
    async for msg in get_consumer():
        try:
            result = await handler(msg.value)
            if result == QueueMessageStatus.CONSUMED:
                await get_consumer().commit()
        except Exception as e:
            logger.exception(f"Error processing message from topic `truck-assignment-completed`: {e}")


async def stop_consuming() -> None:
    consume_task = get_consume_task()
    consume_task.cancel()
    await asyncio.gather(consume_task, return_exceptions=True)

    global _consume_task
    _consume_task = None

    await get_consumer().stop()

    global _consumer
    _consumer = None


class QueueMessageStatus(Enum):
    CONSUMED = auto()
    FAILED = auto()


# =============== Producer ===============
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
