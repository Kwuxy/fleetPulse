import logging

from app.models.journey import Journey

logger = logging.getLogger(__name__)


async def save_journey(journey: Journey) -> None:
    logger.info("Saving journey: %s", journey)
