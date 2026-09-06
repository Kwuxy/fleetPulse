import asyncio

import pytest
import pytest_asyncio
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.kafka import KafkaContainer
from testcontainers.community.postgres import PostgresContainer

from app.clients import db_client
import app.models.orm.delivery  # noqa: F401 - registers Delivery on Base.metadata

TOPICS = ("truck-assignment-requested", "truck-assignment-completed")


@pytest.fixture(scope="module")
def kafka_bootstrap_servers():
    with KafkaContainer().with_kraft().with_env("KAFKA_HEAP_OPTS", "-Xmx512m -Xms512m") as container:
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


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def postgres_db():
    with PostgresContainer(driver="asyncpg") as container:
        database_url = URL.create(
            drivername="postgresql+asyncpg",
            username=container.username,
            password=container.password,
            host=container.get_container_host_ip(),
            port=int(container.get_exposed_port(container.port)),
            database=container.dbname,
        )

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(db_client, "_build_database_url", lambda: database_url)

        schema_engine = create_async_engine(database_url)
        try:
            async with schema_engine.begin() as conn:
                await conn.run_sync(db_client.Base.metadata.create_all)
        finally:
            await schema_engine.dispose()

        await db_client.start_db()

        yield

        await db_client.stop_db()
        monkeypatch.undo()
