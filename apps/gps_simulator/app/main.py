import asyncio
import logging
import os

from app.clients import kafka_client
from app.consumers import departure_consumer

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(levelname)-8s %(message)s",
)

logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("gps_simulator started")
    await kafka_client.start_consuming(departure_consumer.handle_truck_departure_scheduled)

    # TODO: Add alive loop

    await kafka_client.stop_consuming()

if __name__ == "__main__":
    asyncio.run(main())
