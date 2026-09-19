import asyncio
import logging

from app.models.truck_departure import TruckDepartureScheduled

logger = logging.getLogger(__name__)


async def produce_truck_departure_scheduled(request: TruckDepartureScheduled) -> None:
    pass
