import asyncio
import json

import pytest
import pytest_asyncio
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from testcontainers.community.kafka import KafkaContainer

from app.clients import kafka_client
from app.consumers.assignment_consumer import handle_truck_assignment_requested

TOPICS = ("truck-assignment-requested", "truck-assignment-completed")


@pytest.fixture(scope="module")
def kafka_bootstrap_servers():
    with KafkaContainer().with_kraft().with_env("KAFKA_HEAP_OPTS", "-Xmx512m -Xms512m") as container:
        bootstrap_servers = container.get_bootstrap_server()
        asyncio.run(_create_topics(bootstrap_servers))
        yield bootstrap_servers


@pytest.fixture(autouse=True)
def mock_kafka_bootstrap_servers(monkeypatch, kafka_bootstrap_servers):
    monkeypatch.setattr(kafka_client, "KAFKA_BOOTSTRAP_SERVERS", kafka_bootstrap_servers)


@pytest_asyncio.fixture(autouse=True)
async def running_assignment_consumer_and_producer():
    await kafka_client.start_producer()
    await kafka_client.start_consuming(handle_truck_assignment_requested)
    yield
    await kafka_client.stop_consuming()
    await kafka_client.stop_producer()


@pytest_asyncio.fixture()
async def kafka_consumer(kafka_bootstrap_servers):
    kafka_consumer = AIOKafkaConsumer(
        "truck-assignment-completed",
        bootstrap_servers=kafka_bootstrap_servers,
        key_deserializer=lambda key: key.decode("utf-8") if key else None,
        value_deserializer=lambda value: json.loads(value) if value else None,
        auto_offset_reset="latest",
    )
    await kafka_consumer.start()
    yield kafka_consumer
    await kafka_consumer.stop()


@pytest_asyncio.fixture()
async def kafka_producer(kafka_bootstrap_servers):
    kafka_producer = AIOKafkaProducer(
        bootstrap_servers=kafka_bootstrap_servers,
        key_serializer=lambda key: key.encode("utf-8") if key else None,
        value_serializer=lambda value: json.dumps(value).encode("utf-8") if value else None,
    )
    await kafka_producer.start()
    yield kafka_producer
    await kafka_producer.stop()


async def _create_topics(bootstrap_servers: str) -> None:
    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap_servers)
    await admin.start()
    try:
        await admin.create_topics(
            [NewTopic(name=topic, num_partitions=1, replication_factor=1) for topic in TOPICS]
        )
    finally:
        await admin.close()
