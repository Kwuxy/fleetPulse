import asyncio

import pytest
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from testcontainers.community.kafka import KafkaContainer

TOPICS = ("truck-assignment-requested", "truck-assignment-completed")


@pytest.fixture(scope="module")
def kafka_bootstrap_servers():
    with KafkaContainer().with_kraft() as container:
        bootstrap_servers = container.get_bootstrap_server()
        asyncio.run(_create_topics(bootstrap_servers))
        yield bootstrap_servers


async def _create_topics(bootstrap_servers: str) -> None:
    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap_servers)
    await admin.start()
    try:
        await admin.create_topics(
            [NewTopic(name=topic, num_partitions=1, replication_factor=1) for topic in TOPICS]
        )
    finally:
        await admin.close()
