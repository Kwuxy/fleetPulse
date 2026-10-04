import logging

from sqlalchemy import delete, select

from app.models.journey import Journey
from app.models.orm.journey import Journey as JourneyORM, CoordinatesORM
from app.models.truck_departure import Coordinates
from app.clients import db_client

logger = logging.getLogger(__name__)


async def save_journey(journey: Journey) -> None:
    orm_journey = _journey_to_orm(journey)
    async with db_client.get_session() as session:
        await session.merge(orm_journey)


async def clear() -> None:
    async with db_client.get_session() as session:
        await session.execute(delete(JourneyORM))


async def get_journeys() -> list[Journey]:
    async with db_client.get_session() as session:
        result = await session.execute(select(JourneyORM))
        orm_journeys = result.scalars().all()
        return [_journey_from_orm(orm_journey) for orm_journey in orm_journeys]


async def get_journey_by_delivery_id(delivery_id: str) -> Journey | None:
    async with db_client.get_session() as session:
        orm_journey = await session.get(JourneyORM, delivery_id)
        return _journey_from_orm(orm_journey) if orm_journey else None


def _journey_to_orm(journey: Journey) -> JourneyORM:
    return JourneyORM(
        delivery_id=journey.delivery_id,
        truck_id=journey.truck_id,
        pickup_location=_coordinates_to_orm(journey.pickup_location),
        dropoff_location=_coordinates_to_orm(journey.dropoff_location),
        departure_time=journey.departure_time,
    )


def _coordinates_to_orm(coord: Coordinates) -> CoordinatesORM:
    return CoordinatesORM(
        lat=coord.lat,
        lon=coord.lon,
    )


def _journey_from_orm(orm_journey: JourneyORM) -> Journey:
    return Journey(
        delivery_id=orm_journey.delivery_id,
        truck_id=orm_journey.truck_id,
        pickup_location=_coordinates_from_orm(orm_journey.pickup_location),
        dropoff_location=_coordinates_from_orm(orm_journey.dropoff_location),
        departure_time=orm_journey.departure_time,
    )


def _coordinates_from_orm(coord_orm: CoordinatesORM) -> Coordinates:
    return Coordinates(
        lat=coord_orm.lat,
        lon=coord_orm.lon,
    )
