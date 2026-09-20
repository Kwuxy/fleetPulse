import asyncio
import logging
import os
import signal

from app.clients import kafka_client
from app.consumers import departure_consumer

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(levelname)-8s %(message)s",
)

logger = logging.getLogger(__name__)


async def keep_app_alive() -> None:
    shutdown_event = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        logger.info(f"gps_simulator received signal {sig}")
        try:
            asyncio.get_running_loop().add_signal_handler(sig, shutdown_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: shutdown_event.set())

    await shutdown_event.wait()


async def main() -> None:
    logger.info("gps_simulator started")
    await kafka_client.start_consuming(departure_consumer.handle_truck_departure_scheduled)
    await keep_app_alive()
    await kafka_client.stop_consuming()
    logger.info("gps_simulator ended")


if __name__ == "__main__":
    asyncio.run(main())
