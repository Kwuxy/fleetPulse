import asyncio
import logging
import os

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(levelname)-8s %(message)s",
)

logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("gps_simulator started")


if __name__ == "__main__":
    asyncio.run(main())
